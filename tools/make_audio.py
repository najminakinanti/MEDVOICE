"""Buat audio percakapan simulasi dari naskah (suara TTS Indonesia, butuh internet).

  pip install edge-tts av
  python tools/make_audio.py samples/naskah_hendra.txt samples/hendra
Hasil: <out>/dokter.wav, pasien.wav (dua kanal, label pembicara pasti) dan mixed.wav (satu mikrofon), 16 kHz mono.
Naskah: tiap baris 'Dokter: ...' atau 'Pasien: ...'. HANYA untuk naskah fiktif: teks dikirim ke layanan TTS Microsoft."""
import argparse
import asyncio
import io
import re
import sys
import wave
from pathlib import Path

import av
import edge_tts

VOICES = {"dokter": "id-ID-GadisNeural", "pasien": "id-ID-ArdiNeural"}
RATE = 16000


def decode(mp3: bytes) -> bytes:
    """mp3 -> PCM 16-bit mono 16 kHz."""
    out = bytearray()
    with av.open(io.BytesIO(mp3)) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        for frame in c.decode(audio=0):
            for f in rs.resample(frame):
                out += bytes(f.planes[0])[: f.samples * 2]
        for f in rs.resample(None):
            out += bytes(f.planes[0])[: f.samples * 2]
    return bytes(out)


async def synth(text: str, voice: str, rate: str) -> bytes:
    data = b""
    async for ch in edge_tts.Communicate(text, voice, rate=rate).stream():
        if ch["type"] == "audio":
            data += ch["data"]
    return data


def write(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("naskah")
    ap.add_argument("out")
    ap.add_argument("--rate", default="-5%", help="kecepatan bicara TTS, mis. -10%% lebih lambat")
    ap.add_argument("--gap-ms", type=int, default=600)
    a = ap.parse_args()
    lines = []
    for ln in Path(a.naskah).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(Dokter|Pasien)\s*:\s*(.+)$", ln, re.I)
        if m:
            lines.append((m.group(1).lower(), m.group(2).strip()))
    if not lines:
        print("naskah kosong")
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    chan = {"dokter": bytearray(), "pasien": bytearray()}
    gap = b"\x00\x00" * int(RATE * a.gap_ms / 1000)
    for i, (spk, text) in enumerate(lines, 1):
        pcm = decode(await synth(text, VOICES[spk], a.rate)) + gap
        other = "pasien" if spk == "dokter" else "dokter"
        chan[spk] += pcm
        chan[other] += b"\x00" * len(pcm)
        print(f"{i}/{len(lines)} {spk}: {len(pcm) / RATE / 2:.1f}s", flush=True)
    write(out / "dokter.wav", bytes(chan["dokter"]))
    write(out / "pasien.wav", bytes(chan["pasien"]))
    # satu mikrofon: jumlahkan kedua kanal (tidak tumpang tindih, jadi aman)
    import array
    d, p = array.array("h", bytes(chan["dokter"])), array.array("h", bytes(chan["pasien"]))
    mix = array.array("h", (x + y for x, y in zip(d, p)))
    write(out / "mixed.wav", mix.tobytes())
    print(f"selesai: {len(d) / RATE / 60:.1f} menit -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
