"""Layanan STT: faster-whisper + VAD Silero (bawaan faster-whisper, vad_filter).

Dua model: STT_MODEL untuk transkrip FINAL (akurat) dan STT_LIVE_MODEL (kecil/cepat) untuk pratinjau langsung.
Tidak pernah menulis/log isi transkrip. File audio sementara dihapus segera setelah diproses."""
import contextlib
import gc
import os
import re
import shutil
import tempfile
import threading
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket

from stream import handle_stream

app = FastAPI(title="MedVoice STT")
MODEL_NAME = os.environ.get("STT_MODEL", "small")
LIVE_MODEL_NAME = os.environ.get("STT_LIVE_MODEL", "base")       # teks cepat tepat setelah kalimat selesai
REFINE_MODEL_NAME = os.environ.get("STT_REFINE_MODEL", "small")  # perhalusan saat ada jeda
PARTIAL_MODEL_NAME = os.environ.get("STT_PARTIAL_MODEL", "base")   # teks sementara saat bicara (paling cepat)
STREAM_FINAL_MODEL = os.environ.get("STT_STREAM_FINAL_MODEL", "") or REFINE_MODEL_NAME   # teks akhir per ucapan (WebSocket /stream)
# Model teks SEMENTARA streaming (kosong = STT_PARTIAL_MODEL). Sama dengan model final => instance terpisah + teks sementara dipakai sbg final.
STREAM_PARTIAL_MODEL = os.environ.get("STT_STREAM_PARTIAL_MODEL", "") or PARTIAL_MODEL_NAME
STREAM_FINAL_BEAM = int(os.environ.get("STT_STREAM_FINAL_BEAM", "1"))
DEVICE = os.environ.get("STT_DEVICE", "cpu")
COMPUTE = os.environ.get("STT_COMPUTE_TYPE", "int8")
SPLIT_GAP_S = float(os.environ.get("STT_SPLIT_GAP_MS", "1000")) / 1000.0   # jeda >= ini = giliran bicara baru
IDLE_UNLOAD_S = float(os.environ.get("STT_IDLE_UNLOAD_S", "0"))    # >0: bongkar model dari VRAM bila menganggur
PRELOAD = os.environ.get("STT_PRELOAD", "0" if DEVICE == "cuda" else "1") == "1"
# Docker: /models & /tmp/stt. Lokal (Windows/Linux tanpa Docker): cache Hugging Face bawaan & folder temp sistem.
MODELS_DIR = os.environ.get("STT_MODELS_DIR") or ("/models" if os.path.isdir("/models") else None)
TMP_DIR = os.environ.get("STT_TMP_DIR") or ("/tmp/stt" if os.path.isdir("/tmp/stt") else tempfile.gettempdir())
_inflight = 0
_last_used = time.time()
_state = threading.Lock()
_models: dict[str, object] = {}
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def get_model(name: str, wait: bool = True):
    """Muat model (unduh bila belum ada). Kunci PER MODEL: unduhan model pratinjau tidak memblokir transkrip final.
    wait=False: kembalikan None bila model masih dimuat (agar pratinjau gagal cepat, bukan menggantung)."""
    if name in _models:
        return _models[name]
    with _guard:
        lock = _locks.setdefault(name, threading.Lock())
    if not wait and lock.locked():
        return None
    with lock:
        if name not in _models:
            from faster_whisper import WhisperModel
            # "small#p" = instance terpisah dari model yang sama (agar teks sementara & final bisa jalan paralel)
            _models[name] = WhisperModel(name.split("#")[0], device=DEVICE, compute_type=COMPUTE, download_root=MODELS_DIR)
        return _models[name]


def unload_models() -> list[str]:
    """Bebaskan model (dan VRAM). Hanya bila tidak ada transkripsi berjalan."""
    with _state:
        if _inflight:
            return []
        names = sorted(_models)
        _models.clear()
    gc.collect()
    return names


def _janitor() -> None:
    while True:
        time.sleep(5)
        if IDLE_UNLOAD_S > 0 and _models and not _inflight and time.time() - _last_used > IDLE_UNLOAD_S:
            if unload_models():
                print("model_dibongkar_karena_menganggur", flush=True)


def _load_all() -> None:
    for name in dict.fromkeys((LIVE_MODEL_NAME, MODEL_NAME) if DEVICE == "cuda"
                              else (LIVE_MODEL_NAME, PARTIAL_MODEL_NAME, REFINE_MODEL_NAME, MODEL_NAME)):
        for attempt in range(1, 31):
            try:
                get_model(name)
                break
            except Exception as e:  # noqa: BLE001
                print(f"muat_gagal model={name} percobaan={attempt} galat={type(e).__name__}", flush=True)
                time.sleep(20)


def _preload() -> None:
    """Muat model di latar belakang; ulangi bila unduhan gagal (jaringan putus). Unduhan HF melanjutkan dari sisa."""
    import time
    for name in dict.fromkeys((LIVE_MODEL_NAME, PARTIAL_MODEL_NAME, REFINE_MODEL_NAME, MODEL_NAME)):     # pratinjau dulu, lalu model final
        for attempt in range(1, 31):
            try:
                get_model(name)
                break
            except Exception as e:  # noqa: BLE001
                print(f"preload_gagal model={name} percobaan={attempt} galat={type(e).__name__}", flush=True)
                time.sleep(20)


@contextlib.contextmanager
def track():
    """Tandai pekerjaan berjalan (janitor tidak membongkar model selama ada)."""
    global _inflight, _last_used
    with _state:
        _inflight += 1
    try:
        yield
    finally:
        with _state:
            _inflight -= 1
            _last_used = time.time()


@app.websocket("/stream")
async def stream(ws: WebSocket):
    """Transkripsi streaming untuk pratinjau langsung (lihat stream.py)."""
    await handle_stream(ws, get_model=get_model, is_hallucination=is_hallucination, partial_model=STREAM_PARTIAL_MODEL + ("#p" if STREAM_PARTIAL_MODEL == STREAM_FINAL_MODEL else ""),
                        final_model=STREAM_FINAL_MODEL, language=os.environ.get("STT_LANGUAGE", "id"),
                        final_beam=STREAM_FINAL_BEAM, track=track)


@app.on_event("startup")
def _startup() -> None:
    if PRELOAD:
        threading.Thread(target=_preload, daemon=True).start()
    threading.Thread(target=_janitor, daemon=True).start()


@app.post("/warmup")
def warmup():
    """Muat model di latar belakang (dipanggil saat rekaman akan dimulai)."""
    global _last_used
    _last_used = time.time()
    threading.Thread(target=_load_all, daemon=True).start()
    return {"status": "loading", "device": DEVICE}


@app.post("/unload")
def unload():
    """Bebaskan VRAM (dipanggil sebelum LLM bekerja)."""
    names = unload_models()
    return {"unloaded": names, "busy": bool(_inflight)}


HALLUCINATION = re.compile(
    r"(terima kasih (telah|sudah|atas) (menonton|menyaksikan|mendengarkan)|sampai jumpa( di| pada| lagi di)? "
    r"(video|episode)|(video|episode) (selanjutnya|berikutnya)|jangan lupa (untuk )?(like|subscribe|berlangganan)"
    r"|subtitle(s)? (by|oleh)|diterjemahkan oleh|amara\.org|thanks? for watching|see you (in|on) the next"
    r"|please subscribe)", re.I)


def is_hallucination(text: str, seg=None) -> bool:
    """Whisper sering 'mengarang' kalimat penutup video pada hening/derau. Buang yang pasti bukan percakapan klinis,
    atau segmen yang model sendiri nilai kemungkinan besar bukan ucapan."""
    if HALLUCINATION.search(text):
        return True
    return seg is not None and getattr(seg, "no_speech_prob", 0.0) > 0.6 and getattr(seg, "avg_logprob", 0.0) < -0.8


def utterances(segments, gap_s: float) -> list[dict]:
    """Pecah segmen Whisper menjadi ucapan per giliran bicara memakai timestamp per kata: jeda panjang
    (mis. saat lawan bicara berbicara di kanal lain) memulai ucapan baru. Tanpa timestamp kata: pakai segmen apa adanya."""
    out: list[dict] = []
    for s in segments:
        if is_hallucination(s.text, s):
            continue
        words = getattr(s, "words", None)
        if not words:
            if s.text.strip():
                out.append({"start_ms": int(s.start * 1000), "end_ms": int(s.end * 1000), "text": s.text.strip()})
            continue
        cur, prev_end = [], None
        for w in words:
            if cur and prev_end is not None and w.start - prev_end >= gap_s:
                out.append({"start_ms": int(cur[0].start * 1000), "end_ms": int(cur[-1].end * 1000),
                            "text": "".join(x.word for x in cur).strip()})
                cur = []
            cur.append(w)
            prev_end = w.end
        if cur:
            out.append({"start_ms": int(cur[0].start * 1000), "end_ms": int(cur[-1].end * 1000),
                        "text": "".join(x.word for x in cur).strip()})
    return [u for u in out if u["text"]]


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "live_model": LIVE_MODEL_NAME, "refine_model": REFINE_MODEL_NAME, "partial_model": PARTIAL_MODEL_NAME, "stream_partial_model": STREAM_PARTIAL_MODEL, "stream_final_model": STREAM_FINAL_MODEL, "device": DEVICE,
            "loaded": sorted(_models), "ready": MODEL_NAME in _models, "live_ready": LIVE_MODEL_NAME in _models,
            "inflight": _inflight}


@app.post("/transcribe")
def transcribe(file: UploadFile = File(...), language: str = Form("id"), initial_prompt: str = Form(""),
               live: str = Form("")):
    """Sinkron (dijalankan di threadpool) agar pratinjau langsung tidak terblokir transkripsi panjang."""
    global _inflight, _last_used
    name = {"p": PARTIAL_MODEL_NAME, "r": REFINE_MODEL_NAME}.get(live, LIVE_MODEL_NAME if live else MODEL_NAME)
    with _state:
        _inflight += 1
    fd, path = tempfile.mkstemp(dir=TMP_DIR, suffix=os.path.splitext(file.filename or "")[1] or ".bin")
    try:
        with os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            model = get_model(name, wait=not live)
            if model is None:
                raise HTTPException(503, "model_loading")
            segments, info = model.transcribe(
                path, language=language or None, initial_prompt=initial_prompt or None, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300 if live else 500},
                beam_size=1 if live else 5, condition_on_previous_text=False, word_timestamps=not live,
                no_speech_threshold=0.6, **({} if live else {"hallucination_silence_threshold": 1.0}))
            out = utterances(segments, 0.0 if live else SPLIT_GAP_S) if not live else [
                {"start_ms": int(s.start * 1000), "end_ms": int(s.end * 1000), "text": s.text.strip()}
                for s in segments if s.text.strip() and not is_hallucination(s.text, s)]
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, "transcribe_failed:" + type(e).__name__) from None
        return {"model": name, "language": info.language, "segments": out}
    finally:
        with _state:
            _inflight -= 1
            _last_used = time.time()
        try:
            os.remove(path)
        except OSError:
            pass
