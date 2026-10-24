"""Bandingkan WER antar model STT. Folder berisi pasangan  nama.wav|mp3|webm  +  nama.txt (referensi).

  python -m evaluation.stt_wer --audio-dir rekaman_uji --models small,medium,large-v3-turbo --device cpu
Butuh `pip install faster-whisper`. Pakai rekaman SIMULASI/anonim saja."""
import argparse
import time
from pathlib import Path

from .metrics import wer

AUDIO_EXT = {".wav", ".mp3", ".webm", ".m4a", ".ogg", ".flac"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--language", default="id")
    ap.add_argument("--prompt-file", help="initial_prompt (kosakata medis); kosong = tanpa prompt")
    a = ap.parse_args(argv)
    from faster_whisper import WhisperModel
    prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else None
    pairs = [(p, p.with_suffix(".txt")) for p in sorted(Path(a.audio_dir).iterdir())
             if p.suffix.lower() in AUDIO_EXT and p.with_suffix(".txt").exists()]
    if not pairs:
        print("Tidak ada pasangan audio+txt")
        return 2
    print("| model | file | WER | detik |\n|---|---|---|---|")
    for m in a.models.split(","):
        model = WhisperModel(m, device=a.device, compute_type=a.compute_type)
        scores = []
        for audio, ref in pairs:
            t0 = time.time()
            segs, _ = model.transcribe(str(audio), language=a.language, initial_prompt=prompt, vad_filter=True,
                                       condition_on_previous_text=False)
            hyp = " ".join(s.text for s in segs)
            w = wer(ref.read_text(encoding="utf-8"), hyp)
            scores.append(w)
            print(f"| {m} | {audio.name} | {w:.3f} | {time.time() - t0:.1f} |")
        print(f"| **{m}** | rata-rata | **{sum(scores) / len(scores):.3f}** | |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
