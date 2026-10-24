"""Uji UI: unggah file audio dokter+pasien (atau campuran) -> review. Menghitung WER transkrip vs naskah.

  MV_CLIENT=rs-dev MV_USER=drdev MV_PASSWORD=... python tools/browser_upload_e2e.py --dir samples/hendra --naskah samples/naskah_hendra.txt --out shots/"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/x")
from browser_e2e import login  # noqa: E402
from evaluation.metrics import wer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--naskah")
    ap.add_argument("--out", default="shots")
    ap.add_argument("--mixed", action="store_true", help="unggah mixed.wav saja")
    ap.add_argument("--base", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    ap.add_argument("--wait", type=int, default=1500)
    a = ap.parse_args()
    d, out = Path(a.dir), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        login(page, a.base)
        page.click('button:has-text("Sesi Manual")')
        page.fill("#nr", "UPLOAD/0001")
        page.locator("[role=dialog] .check input").first.check()
        page.click('button:has-text("Setuju & Mulai Rekam")')
        page.wait_for_selector("text=Siap merekam")
        page.click("summary:has-text('unggah file audio')")
        files = page.locator(".up input[type=file]")
        if a.mixed:
            files.nth(2).set_input_files(str(d / "mixed.wav"))
        else:
            files.nth(0).set_input_files(str(d / "dokter.wav"))
            files.nth(1).set_input_files(str(d / "pasien.wav"))
        t0 = time.time()
        page.click('button:has-text("Unggah & proses")')
        page.wait_for_selector("[role=tablist]", timeout=a.wait * 1000)
        print(f"hasil muncul setelah {time.time() - t0:.0f}s")
        page.click('button[role=tab]:has-text("Transkrip")')
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "u_transkrip.png"), full_page=True)
        segs = page.locator(".trl .row")
        hyp = " ".join(segs.nth(i).locator(".txt").inner_text() for i in range(segs.count()))
        print(f"segmen transkrip: {segs.count()}")
        (out / "u_transkrip.txt").write_text("\n".join(
            segs.nth(i).inner_text().replace("\n", " ") for i in range(segs.count())), encoding="utf-8")
        if a.naskah:
            ref = " ".join(re.sub(r"^\s*(Dokter|Pasien)\s*:\s*", "", l) for l in Path(a.naskah).read_text(encoding="utf-8").splitlines())
            print(f"WER transkrip vs naskah: {wer(ref, hyp):.3f}")
        page.click('button[role=tab]:has-text("SOAP")')
        page.wait_for_selector("text=Subjektif")
        page.screenshot(path=str(out / "u_soap.png"), full_page=True)
        print("SOAP:")
        for i in range(page.locator(".se textarea").count()):
            print("  -", page.locator(".se textarea").nth(i).input_value())
        print("KODE:", [page.locator(".codes .cd").nth(i).inner_text().replace("\n", " | ") for i in range(page.locator(".codes .cd").count())])
        print("galat JS:", errors or "tidak ada")
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
