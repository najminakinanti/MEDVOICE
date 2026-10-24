"""Transkripsi streaming lewat WebSocket (/stream). HANYA untuk pratinjau langsung: tidak ada audio/teks yang disimpan.

Protokol (klien = engine API, yang meneruskan dari browser):
  teks  {"t":"config","language":"id","prompt":"..."}        sekali, di awal
  teks  {"t":"start","ch":0,"id":7,"start_ms":12340}          ucapan baru pada kanal ch
  biner [ch:uint8][PCM 16-bit mono 16 kHz little-endian]      audio ucapan yang sedang berjalan
  teks  {"t":"end","ch":0,"id":7}                              ucapan selesai -> hasil akhir
Server -> klien:
  {"t":"status","state":"loading"|"ready"}
  {"t":"partial","ch","id","stable","tail","ms"}  teks sementara; `stable` = kata yang sama di dua hipotesis berturut-turut
  {"t":"final","ch","id","text","ms"}              teks akhir (model lebih akurat); menggantikan teks sementara
  (`ms` = lama inferensi; untuk pemantauan kinerja, tanpa isi percakapan)
  {"t":"drop","ch","id"}                       tidak ada ucapan nyata (derau/halusinasi): hapus gelembung

Penjadwalan: DUA pekerja per koneksi (satu khusus hasil akhir, satu khusus teks sementara) supaya teks akhir yang
lambat (model lebih besar) tidak membuat teks sementara kelaparan. Teks sementara hanya "terbaru yang menang"
(audio terkini dibaca saat giliran berjalan, bukan saat dijadwalkan) sehingga tidak ada antrean usang."""
import asyncio
import json
import re
import logging
import threading
import time
import traceback
from collections import deque

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger("uvicorn.error")
SR = 16000
BYTES_PER_S = SR * 2
STEP_S = 0.5            # jarak minimal antar teks sementara (audio baru yang terkumpul)
MIN_PARTIAL_S = 0.45    # ucapan lebih pendek dari ini belum layak ditranskripsi
MAX_UTT_S = 30          # batas keras satu ucapan
REUSE_TOLERANCE_S = 0.7 # sisa audio (hening penutup) yang boleh tidak tercakup agar teks sementara dipakai sbg final
_WORD = re.compile(r"[^\w]+", re.UNICODE)
# Parameter VAD Silero bawaan faster-whisper (nama kolom VadOptions; diuji di test_stt_stream.py)
VAD_PARAMS = {"onset": 0.3, "offset": 0.2, "min_silence_duration_ms": 300, "speech_pad_ms": 250}
_MODEL_LOCKS: dict[str, threading.Lock] = {}


def _norm(w: str) -> str:
    return _WORD.sub("", w.lower())


def split_stable(prev: list[str], cur: list[str]) -> tuple[list[str], list[str]]:
    """LocalAgreement-2: awalan kata yang sama pada dua hipotesis berturut-turut dianggap stabil."""
    n = 0
    for a, b in zip(prev, cur):
        if _norm(a) != _norm(b) or not _norm(a):
            break
        n += 1
    return cur[:n], cur[n:]


class _Utt:
    __slots__ = ("ch", "id", "pcm", "sched_len", "pending", "ended", "prev_words", "last_sent", "last_cover")

    def __init__(self, ch: int, uid: int):
        self.ch, self.id = ch, uid
        self.pcm = bytearray()
        self.sched_len = 0
        self.pending = False
        self.ended = False
        self.prev_words: list[str] = []
        self.last_sent = ""
        self.last_cover = 0                 # panjang audio (byte) yang dicakup teks sementara terakhir


class StreamSession:
    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop, *, get_model, is_hallucination,
                 partial_model: str, final_model: str, language: str, final_beam: int, track):
        self.ws, self.loop = ws, loop
        self.get_model, self.is_hallu, self.track = get_model, is_hallucination, track
        self.partial_model, self.final_model = partial_model, final_model
        self.language, self.final_beam, self.prompt = language, final_beam, ""
        self.out: asyncio.Queue = asyncio.Queue()
        self.cur: dict[int, _Utt] = {}                  # utt aktif per kanal
        self.finals: deque[_Utt] = deque()
        self.partials: "dict[tuple[int, int], _Utt]" = {}
        self.cv = threading.Condition()
        self.closed = False
        self.same_model = partial_model.split("#")[0] == final_model.split("#")[0]
        self.history: deque[str] = deque(maxlen=2)

    # ---- keluar
    def emit(self, obj: dict) -> None:
        if not self.closed:
            self.loop.call_soon_threadsafe(self.out.put_nowait, json.dumps(obj, ensure_ascii=False))

    # ---- masuk (dipanggil dari event loop)
    def on_start(self, ch: int, uid: int) -> None:
        with self.cv:
            old = self.cur.get(ch)
            if old and not old.ended:               # klien lupa mengakhiri: akhiri otomatis
                self._end_locked(old)
            self.cur[ch] = _Utt(ch, uid)

    def on_audio(self, ch: int, data: bytes) -> None:
        with self.cv:
            u = self.cur.get(ch)
            if not u or u.ended or len(u.pcm) + len(data) > MAX_UTT_S * BYTES_PER_S:
                return
            u.pcm += data[: len(data) - (len(data) % 2)]
            self._maybe_partial_locked(u)

    def on_end(self, ch: int, uid: int) -> None:
        with self.cv:
            u = self.cur.get(ch)
            if u and u.id == uid and not u.ended:
                self._end_locked(u)

    def _end_locked(self, u: _Utt) -> None:
        u.ended = True
        self.partials.pop((u.ch, u.id), None)
        if len(u.pcm) >= MIN_PARTIAL_S * BYTES_PER_S:
            self.finals.append(u)
            self.cv.notify_all()   # dua pekerja menunggu pada cv yang sama
        else:
            self.emit({"t": "drop", "ch": u.ch, "id": u.id})

    def _maybe_partial_locked(self, u: _Utt) -> None:
        if u.pending or u.ended:
            return
        n = len(u.pcm)
        if n >= MIN_PARTIAL_S * BYTES_PER_S and n - u.sched_len >= STEP_S * BYTES_PER_S:
            u.pending = True
            self.partials[(u.ch, u.id)] = u
            self.cv.notify_all()   # dua pekerja menunggu pada cv yang sama

    def close(self) -> None:
        with self.cv:
            self.closed = True
            self.cv.notify_all()

    # ---- pekerja (thread)
    def _next(self, kind: str):
        with self.cv:
            while not self.closed:
                if kind == "final" and self.finals:
                    return self.finals.popleft()
                if kind == "partial" and self.partials:
                    return self.partials.pop(next(iter(self.partials)))      # yang paling lama menunggu
                self.cv.wait()
        return None

    def start(self) -> None:
        """Muat model (sekali) lalu jalankan dua pekerja. Dipanggil dari event loop; tidak memblokir."""
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        for name in dict.fromkeys((self.partial_model, self.final_model)):
            self.emit({"t": "status", "state": "loading"})
            try:
                self.get_model(name)
            except Exception:  # noqa: BLE001
                self.emit({"t": "error", "code": "model_load_failed"})
                return
        self.emit({"t": "status", "state": "ready"})
        for kind in ("final", "partial"):
            threading.Thread(target=self.worker, args=(kind,), daemon=True).start()

    def worker(self, kind: str) -> None:
        # model yang sama dipakai oleh dua pekerja (partial_model == final_model) tidak boleh dipakai bersamaan
        lock = _MODEL_LOCKS.setdefault(self.final_model, threading.Lock()) if self.partial_model == self.final_model else None
        while True:
            u = self._next(kind)
            if u is None:
                return
            try:
                with self.track():
                    if lock:
                        with lock:
                            (self._run_final if kind == "final" else self._run_partial)(u)
                    else:
                        (self._run_final if kind == "final" else self._run_partial)(u)
            except Exception as e:  # noqa: BLE001
                log.error("stream_%s_gagal %s", kind, traceback.format_exc(limit=3))   # tanpa isi percakapan
                self.emit({"t": "error", "code": type(e).__name__})
                if kind == "final":
                    self.emit({"t": "drop", "ch": u.ch, "id": u.id})

    def _audio(self, pcm: bytes) -> np.ndarray:
        return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    def _drop(self, text: str, seg) -> bool:
        """Buang halusinasi pasti (kalimat penutup video) atau segmen yang SANGAT jelas bukan ucapan.
        Lebih longgar dari transkripsi batch: ucapan pendek/pelan dari mikrofon asli sering punya no_speech_prob tinggi."""
        if self.is_hallu(text, None):
            return True
        return getattr(seg, "no_speech_prob", 0.0) > 0.85 and getattr(seg, "avg_logprob", 0.0) < -1.0

    def _prompt(self) -> str:
        """Kosakata medis + dua kalimat terakhir sebagai konteks (meningkatkan konsistensi istilah & ejaan)."""
        ctx = " ".join(self.history)[-240:]
        return (self.prompt + " " + ctx).strip()

    def _decode(self, model_name: str, audio: np.ndarray, *, beam: int, prompt: str, vad: bool) -> str:
        model = self.get_model(model_name)
        # vad=False untuk teks sementara: klien sudah menyaring ucapan; Silero bisa membuang suara pelan sehingga teks kosong.
        segments, _ = model.transcribe(
            audio, language=self.language or None, initial_prompt=prompt or None, beam_size=beam,
            vad_filter=vad, vad_parameters=VAD_PARAMS,
            condition_on_previous_text=False, temperature=0.0, no_speech_threshold=0.7, without_timestamps=True,
            word_timestamps=False)
        parts = [s.text.strip() for s in segments if s.text.strip() and not self._drop(s.text, s)]
        return " ".join(parts).strip()

    def _run_partial(self, u: _Utt) -> None:
        with self.cv:
            snap = bytes(u.pcm)
            u.sched_len = len(snap)
            gone = u.ended or self.closed
        if gone:
            return
        t0 = time.perf_counter()
        text = self._decode(self.partial_model, self._audio(snap), beam=1, prompt=self._prompt(), vad=False)
        ms = round((time.perf_counter() - t0) * 1000)
        with self.cv:
            u.pending = False
            if u.ended or self.closed:
                return
            words = text.split()
            if words and text != u.last_sent:
                stable, tail = split_stable(u.prev_words, words)
                u.prev_words, u.last_sent, u.last_cover = words, text, u.sched_len
                self.emit({"t": "partial", "ch": u.ch, "id": u.id, "stable": " ".join(stable), "tail": " ".join(tail), "ms": ms})
            self._maybe_partial_locked(u)                    # ada audio baru selama inferensi? lanjut segera

    def _run_final(self, u: _Utt) -> None:
        t0 = time.perf_counter()
        n = len(u.pcm)
        # Model teks sementara == model final dan teks sementara sudah mencakup (hampir) seluruh ucapan: pakai langsung,
        # tidak perlu dekode ulang (menghemat ~1-2 dtk di CPU). Sisa audio di ujung hanyalah hening penutup.
        if self.same_model and u.last_sent and u.last_cover >= n - REUSE_TOLERANCE_S * BYTES_PER_S:
            text, ms = u.last_sent, 0
        else:
            text = self._decode(self.final_model, self._audio(bytes(u.pcm)), beam=self.final_beam,
                                prompt=self._prompt(), vad=True)
            ms = round((time.perf_counter() - t0) * 1000)
        if text:
            self.history.append(text)
            self.emit({"t": "final", "ch": u.ch, "id": u.id, "text": text, "ms": ms})
        else:
            self.emit({"t": "drop", "ch": u.ch, "id": u.id})
        with self.cv:
            if self.cur.get(u.ch) is u:
                self.cur.pop(u.ch, None)


async def handle_stream(ws: WebSocket, *, get_model, is_hallucination, partial_model: str, final_model: str,
                        language: str, final_beam: int, track) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    s = StreamSession(ws, loop, get_model=get_model, is_hallucination=is_hallucination, partial_model=partial_model,
                      final_model=final_model, language=language, final_beam=final_beam, track=track)
    s.start()

    async def sender():
        while True:
            await ws.send_text(await s.out.get())

    send_task = asyncio.create_task(sender())
    try:
        with track():                                       # koneksi terbuka = model tidak dibongkar janitor
            while True:
                m = await ws.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("bytes") is not None:
                    b = m["bytes"]
                    if len(b) > 1:
                        s.on_audio(b[0], b[1:])
                    continue
                try:
                    d = json.loads(m.get("text") or "")
                except ValueError:
                    continue
                t = d.get("t")
                if t == "config":
                    s.language = str(d.get("language") or s.language)[:8]
                    s.prompt = str(d.get("prompt") or "")[:2000]
                elif t == "start":
                    s.on_start(int(d.get("ch", 0)), int(d.get("id", 0)))
                elif t == "end":
                    s.on_end(int(d.get("ch", 0)), int(d.get("id", 0)))
                elif t == "bye":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        s.close()
        send_task.cancel()
