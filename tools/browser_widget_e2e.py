"""Uji widget di browser: SERVER (di sini: skrip ini, dengan API key) membuat sesi + token widget; browser hanya menerima token.

  MV_API_KEY=mvk_... python tools/browser_widget_e2e.py --wav mixed.wav --seconds 27 --out shots/"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from browser_e2e import poll  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--seconds", type=int, default=27)
    ap.add_argument("--out", default="shots")
    ap.add_argument("--base", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    ap.add_argument("--doctor", default="DR001")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    hk = {"X-API-Key": os.environ["MV_API_KEY"]}
    sid = httpx.post(a.base + "/v1/sessions", headers=hk, json={
        "no_rawat": "WIDGET/0001", "consent": {"given": True, "recorded_by": "server-rs"},
        "doctor": {"simrs_user_id": a.doctor, "display_name": "dr. Widget"}}).json()["id"]
    tok = httpx.post(f"{a.base}/v1/sessions/{sid}/widget-token", headers=hk).json()["token"]
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                                    f"--use-file-for-fake-audio-capture={a.wav}"])
        ctx = b.new_context(permissions=["microphone"], viewport={"width": 1500, "height": 1100})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append("console: " + m.text))
        page.goto(f"{a.base}/ui/widget-demo.html#session={sid}&token={tok}")
        fr = page.frame_locator("iframe")
        try:
            fr.locator("text=Siap merekam").wait_for(timeout=20000)
        except Exception:
            page.screenshot(path=str(out / "w0_fail.png"), full_page=True)
            print("GAGAL memuat widget. galat:", errors)
            print("iframe src:", page.locator("iframe").get_attribute("src") if page.locator("iframe").count() else "(tidak ada iframe)")
            return 1
        print("login dilewati: widget langsung menampilkan perekaman")
        fr.locator('button:has-text("Mulai Rekam")').click()
        fr.locator("[data-testid=timer]").wait_for(timeout=15000)
        time.sleep(a.seconds)
        fr.locator("[data-testid=stop]").click()
        fr.locator("[data-testid=stop-confirm]").click()
        fr.locator("[role=tablist]").wait_for(timeout=600000)
        page.screenshot(path=str(out / "w1_review.png"), full_page=True)
        fr.locator('button[role=tab]:has-text("SOAP")').click()
        ta = fr.locator(".se textarea").first
        ta.fill(ta.input_value() + " [widget]")
        poll(lambda: "Disimpan otomatis" in fr.locator(".saved").inner_text(), 20)
        fr.locator(".ap .check input").check()
        fr.locator("[data-testid=approve]").click()
        fr.locator("[data-testid=approve-confirm]").click()
        fr.locator("text=Rekam medis terkirim ke SIMRS").wait_for(timeout=30000)
        log = page.inner_text("#log")
        print("event diterima halaman induk:\n" + log)
        page.screenshot(path=str(out / "w2_submitted.png"), full_page=True)
        b.close()
    ok = all(x in log for x in ("review_loaded", "approved", "submitted")) and not errors
    print("galat JS/konsol:", errors or "tidak ada", "| HASIL:", "OK" if ok else "GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
