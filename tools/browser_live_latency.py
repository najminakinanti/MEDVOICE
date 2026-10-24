"""Ukur 'realtime' transkrip langsung (WebSocket): kapan gelembung muncul, teks sementara, teks final.

  MV_CLIENT=rs-dev MV_USER=drdev MV_PASSWORD=... python tools/browser_live_latency.py --wav samples/hendra_klip45s/mixed.wav --seconds 30
Mikrofon palsu memutar WAV mulai saat 'Setuju & Mulai Rekam' diklik (t=0). Sama dengan `browser_e2e.py --latency-only`."""
import sys

from browser_e2e import main

if __name__ == "__main__":
    sys.argv.append("--latency-only")
    sys.exit(main())
