"""Bandingkan model STT pada kanal dokter/pasien dari samples (WER vs naskah). Dijalankan di host (venv), memakai faster-whisper langsung.

  python tools/stt_compare.py --dir samples/hendra --naskah samples/naskah_hendra.txt --models small,large-v3-turbo --device cpu --channel dokter
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")
from app.vocab import initial_prompt  # noqa: E402
from evaluation.metrics import wer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--naskah", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--channel", default="dokter", choices=["dokter", "pasien"])
    ap.add_argument("--no-prompt", action="store_true")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    ref = " ".join(m.group(2) for l in Path(a.naskah).read_text(encoding="utf-8").splitlines()
                   if (m := re.match(r"^\s*(Dokter|Pasien)\s*:\s*(.+)$", l, re.I)) and m.group(1).lower() == a.channel)
    for name in a.models.split(","):
        t0 = time.time()
        model = WhisperModel(name, device=a.device, compute_type=a.compute_type)
        t1 = time.time()
        segs, _ = model.transcribe(str(Path(a.dir) / f"{a.channel}.wav"), language="id", vad_filter=True,
                                   condition_on_previous_text=False, beam_size=5,
                                   initial_prompt=None if a.no_prompt else initial_prompt())
        hyp = " ".join(s.text.strip() for s in segs)
        print(f"{name:18} WER={wer(ref, hyp):.3f}  muat={t1 - t0:.0f}s  transkripsi={time.time() - t1:.0f}s", flush=True)
        (Path(a.dir) / f"hasil_{name}_{a.channel}.txt").write_text(hyp, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
