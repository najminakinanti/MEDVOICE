"""Logika streaming STT (stream.py) dengan model palsu: penjadwalan 'terbaru menang', stabilitas kata, drop/final."""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stt"))
import stream  # noqa: E402

PCM_1S = b"\x01\x00" * stream.SR


def test_split_stable_awalan_kata_sama():
    assert stream.split_stable([], ["saya", "sakit"]) == ([], ["saya", "sakit"])
    assert stream.split_stable(["saya", "sakit", "kepala"], ["Saya,", "sakit", "kepalaku", "lagi"]) == (
        ["Saya,", "sakit"], ["kepalaku", "lagi"])
    assert stream.split_stable(["a"], []) == ([], [])


class FakeModel:
    def __init__(self, texts, delay=0.0):
        self.texts, self.delay, self.calls = list(texts), delay, 0

    def transcribe(self, audio, **kw):
        time.sleep(self.delay)
        self.calls += 1
        t = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        return iter([NS(text=t, no_speech_prob=0.0, avg_logprob=0.0)] if t else []), None


class FakeWS:
    pass


def _session(models, loop, partial="p", final="f"):
    import contextlib

    @contextlib.contextmanager
    def track():
        yield

    s = stream.StreamSession(FakeWS(), loop, get_model=lambda n: models[n], is_hallucination=lambda t, seg=None: False,
                             partial_model=partial, final_model=final, language="id", final_beam=1, track=track)
    s.start()
    return s


async def _collect(s, until, timeout=5.0):
    got = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = json.loads(await asyncio.wait_for(s.out.get(), 0.2))
        except asyncio.TimeoutError:
            continue
        got.append(m)
        if until(m):
            break
    return got


def test_partial_lalu_final_dan_stabil():
    async def run():
        loop = asyncio.get_running_loop()
        models = {"p": FakeModel(["saya sakit", "saya sakit kepala"]), "f": FakeModel(["Saya sakit kepala."])}
        s = _session(models, loop)
        await _collect(s, lambda m: m.get("state") == "ready")
        s.on_start(0, 1)
        s.on_audio(0, PCM_1S)
        p1 = await _collect(s, lambda m: m["t"] == "partial")
        s.on_audio(0, PCM_1S)
        p2 = await _collect(s, lambda m: m["t"] == "partial")
        s.on_end(0, 1)
        fin = await _collect(s, lambda m: m["t"] in ("final", "drop"))
        s.close()
        return p1[-1], p2[-1], fin[-1]

    p1, p2, fin = asyncio.run(run())
    assert p1["stable"] == "" and p1["tail"] == "saya sakit"           # hipotesis pertama: belum ada kesepakatan
    assert p2["stable"] == "saya sakit" and p2["tail"] == "kepala"     # dua hipotesis sepakat pada awalan
    assert {k: fin[k] for k in ("t", "ch", "id", "text")} == {"t": "final", "ch": 0, "id": 1, "text": "Saya sakit kepala."}
    assert isinstance(fin["ms"], int) and isinstance(p2["ms"], int)


def test_ucapan_terlalu_pendek_dan_kosong_di_drop():
    async def run():
        loop = asyncio.get_running_loop()
        s = _session({"p": FakeModel([""]), "f": FakeModel([""])}, loop)
        await _collect(s, lambda m: m.get("state") == "ready")
        s.on_start(0, 1)
        s.on_audio(0, b"\x01\x00" * 1000)           # < 0,45 dtk
        s.on_end(0, 1)
        a = await _collect(s, lambda m: m["t"] == "drop")
        s.on_start(0, 2)
        s.on_audio(0, PCM_1S)
        s.on_end(0, 2)                             # final kosong (derau)
        b = await _collect(s, lambda m: m["t"] in ("final", "drop") and m["id"] == 2)
        s.close()
        return a[-1], b[-1]

    a, b = asyncio.run(run())
    assert a == {"t": "drop", "ch": 0, "id": 1} and b == {"t": "drop", "ch": 0, "id": 2}


def test_teks_sementara_tidak_menumpuk_saat_model_lambat():
    """Model lambat + audio terus masuk: jumlah inferensi dibatasi (satu pending), bukan satu per potongan audio."""
    async def run():
        loop = asyncio.get_running_loop()
        pm = FakeModel(["a b c"], delay=0.3)
        s = _session({"p": pm, "f": FakeModel(["x"])}, loop)
        await _collect(s, lambda m: m.get("state") == "ready")
        s.on_start(0, 1)
        for _ in range(40):                          # 40 x 0,1 dtk audio masuk dalam sekejap
            s.on_audio(0, PCM_1S[: len(PCM_1S) // 10])
        await asyncio.sleep(1.0)
        s.on_end(0, 1)
        await _collect(s, lambda m: m["t"] == "final")
        s.close()
        return pm.calls

    assert asyncio.run(run()) <= 4


def test_model_sama_teks_sementara_dipakai_sebagai_final_tanpa_dekode_ulang():
    async def run():
        loop = asyncio.get_running_loop()
        fin_model = FakeModel(["TIDAK DIPAKAI"])
        s = _session({"m#p": FakeModel(["saya sakit kepala"]), "m": fin_model}, loop, partial="m#p", final="m")
        await _collect(s, lambda m: m.get("state") == "ready")
        s.on_start(0, 1)
        s.on_audio(0, PCM_1S)
        await _collect(s, lambda m: m["t"] == "partial")
        s.on_end(0, 1)                                  # audio yang dicakup teks sementara = seluruh ucapan
        fin = await _collect(s, lambda m: m["t"] in ("final", "drop"))
        s.close()
        return fin[-1], fin_model.calls

    fin, calls = asyncio.run(run())
    assert fin["text"] == "saya sakit kepala" and fin["ms"] == 0 and calls == 0


def test_konteks_kalimat_sebelumnya_masuk_prompt():
    seen = []

    class Rec(FakeModel):
        def transcribe(self, audio, **kw):
            seen.append(kw.get("initial_prompt"))
            return super().transcribe(audio, **kw)

    async def run():
        loop = asyncio.get_running_loop()
        s = _session({"p": FakeModel(["x"]), "f": Rec(["Tekanan darah 150 per 90."])}, loop)
        s.prompt = "Istilah: hipertensi."
        await _collect(s, lambda m: m.get("state") == "ready")
        for uid in (1, 2):
            s.on_start(0, uid)
            s.on_audio(0, PCM_1S)
            s.on_end(0, uid)
            await _collect(s, lambda m, u=uid: m["t"] == "final" and m["id"] == u)
        s.close()

    asyncio.run(run())
    assert seen[0] == "Istilah: hipertensi."
    assert "Tekanan darah 150 per 90." in seen[1] and seen[1].startswith("Istilah: hipertensi.")


def test_parameter_vad_valid_untuk_faster_whisper_terpasang():
    """Regresi: nama kolom VadOptions berbeda antar versi; salah nama = TypeError di SEMUA teks final."""
    from faster_whisper.vad import VadOptions
    VadOptions(**stream.VAD_PARAMS)
