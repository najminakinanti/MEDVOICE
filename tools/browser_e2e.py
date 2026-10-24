"""Uji UI Vue di browser sungguhan (Chromium + mikrofon palsu yang memutar berkas WAV) + ukur latensi transkrip langsung.

  pip install playwright && python -m playwright install chromium
  MV_CLIENT=rs-dev MV_USER=drdev MV_PASSWORD=... python tools/browser_e2e.py --wav samples/hendra_klip45s/mixed.wav --seconds 30 --out shots/
  ... --latency-only      berhenti setelah tabel waktu (tanpa menunggu LLM/SOAP)

Alur: login -> antrean -> consent -> rekam (transkrip langsung via WebSocket) -> Selesai -> hasil -> SOAP -> setujui & kirim.
Hanya audio SIMULASI. Tangkapan layar tiap tahap disimpan ke --out. Latensi diukur dari DOM (kapan gelembung muncul,
kapan teks sementara pertama, kapan teks akhir) relatif terhadap klik 'Setuju & Mulai Rekam'."""
import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def poll(cond, timeout=20.0, step=0.3):
    """Tunggu kondisi Python (tanpa eval di halaman: CSP aplikasi tetap aktif)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(step)
    raise TimeoutError("kondisi tidak terpenuhi")


def login(page, base):
    page.goto(base + "/ui/")
    page.fill("#lc", os.environ["MV_CLIENT"])
    page.fill("#lu", os.environ["MV_USER"])
    page.fill("#lp", os.environ["MV_PASSWORD"])
    page.click("form button.btn-primary")
    page.wait_for_selector("text=Antrean Poli Umum", timeout=15000)


def start_recording(page):
    """Sesi Manual dengan no. rawat unik (tidak menghabiskan pasien antrean contoh)."""
    page.click('button:has-text("Sesi Manual")')
    page.fill("#nr", f"E2E/{int(time.time())}")
    page.locator("[role=dialog] .check input").first.check()
    t0 = time.time()
    page.click('button:has-text("Setuju & Mulai Rekam")')
    page.wait_for_selector('[data-testid=timer]', timeout=15000)
    return t0


def timeline(page, t0, seconds):
    """Pantau gelembung chat: tiap gelembung dicatat saat muncul, saat teks sementara pertama, saat final."""
    seen = {}
    end = time.time() + seconds
    while time.time() < end:
        rows = page.locator(".chat .row")
        for i in range(rows.count()):
            r = rows.nth(i)
            cls = r.get_attribute("class") or ""
            txt = (r.locator(".txt").inner_text() or "").strip()
            now = round(time.time() - t0, 1)
            e = seen.setdefault(i, {"muncul": now, "teks": ""})
            if "partial" in cls and txt and "sementara" not in e:
                e["sementara"] = now
            if "final" in cls and txt and "final" not in e:
                e["final"] = now
            e["teks"] = txt[:60]
            e["full"] = txt if "final" in cls else e.get("full", "")
        time.sleep(0.2)
    return seen


def approx_wer(seen, naskah):
    """WER perkiraan: gabungan teks FINAL vs awalan naskah (klip 45 dtk = awal naskah; panjang awalan dipilih yang paling cocok).
    Hanya untuk membandingkan konfigurasi pada audio yang sama, bukan angka akurasi mutlak."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")
    import re
    from evaluation.metrics import wer
    hyp = " ".join(e.get("full", "") for _, e in sorted(seen.items()) if e.get("full"))
    ref_words = " ".join(re.sub(r"^\s*(Dokter|Pasien)\s*:\s*", "", l) for l in Path(naskah).read_text(encoding="utf-8").splitlines()).split()
    n = max(1, len(hyp.split()))
    best = min((wer(" ".join(ref_words[:k]), hyp), k) for k in range(int(n * 0.7), min(len(ref_words), int(n * 1.5)) + 1))
    print(f"WER perkiraan (teks final vs awalan naskah, {best[1]} kata): {best[0]:.3f}")
    print("teks final:", hyp)


def print_timeline(seen):
    print("no | muncul | teks sementara | teks final | teks")
    for i, e in sorted(seen.items()):
        print(f"{i:>2} | {e['muncul']:>5}s | {str(e.get('sementara', '-')):>13}s | {str(e.get('final', '-')):>9}s | {e['teks']}")
    ps = [e["sementara"] - e["muncul"] for e in seen.values() if "sementara" in e]
    fs = [e["final"] - e["muncul"] for e in seen.values() if "final" in e]
    if ps:
        print(f"teks sementara pertama muncul {sum(ps) / len(ps):.1f}s (rata-rata) setelah gelembung 'Mendengarkan'")
    if fs:
        print(f"teks final muncul {sum(fs) / len(fs):.1f}s (rata-rata) setelah gelembung muncul")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--out", default="shots")
    ap.add_argument("--base", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    ap.add_argument("--latency-only", action="store_true")
    ap.add_argument("--naskah", help="berkas naskah untuk WER perkiraan (mis. samples/naskah_hendra.txt)")
    ap.add_argument("--wait", type=int, default=420, help="detik maks menunggu pemrosesan SOAP")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                                    f"--use-file-for-fake-audio-capture={a.wav}"])
        ctx = b.new_context(permissions=["microphone"], viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append("console: " + m.text))
        page.on("websocket", lambda ws: print("  ws:", ws.url.split("/v1")[-1]))

        login(page, a.base)
        page.screenshot(path=str(out / "1_antrean.png"))
        t0 = start_recording(page)
        page.screenshot(path=str(out / "2_rekam_mulai.png"))
        seen = timeline(page, t0, a.seconds)
        page.screenshot(path=str(out / "3_rekam_live.png"))
        print_timeline(seen)
        if a.naskah:
            approx_wer(seen, a.naskah)
        assert seen, "tidak ada gelembung transkrip langsung sama sekali"

        if not a.latency_only:
            page.click('[data-testid=stop]')
            page.click('[data-testid=stop-confirm]')
            page.wait_for_selector("text=Memproses rekaman", timeout=30000)
            page.screenshot(path=str(out / "4_proses.png"))
            page.wait_for_selector('[role=tablist]', timeout=a.wait * 1000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / "5_hasil_info.png"))
            page.click('button[role=tab]:has-text("SOAP")')
            page.wait_for_selector("text=Subjektif")
            page.screenshot(path=str(out / "6_soap.png"))
            page.locator(".ap .check input").check()
            page.click('[data-testid=approve]')
            page.click('[data-testid=approve-confirm]')
            page.wait_for_selector("text=Rekam medis terkirim ke SIMRS", timeout=30000)
            page.screenshot(path=str(out / "7_terkirim.png"))
            print("alur penuh OK: rekam -> proses -> review -> approve -> kirim")
        b.close()
    if errors:
        print("GALAT BROWSER:")
        for e in errors:
            print(" ", e[:200])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
