"""Smoke test end-to-end terhadap engine yang sedang jalan (model STT/LLM sungguhan).

  BASE_URL=http://localhost:8000 MV_CLIENT=rs-dev MV_USER=drdev MV_PASSWORD=... \
  python tools/smoke_e2e.py --dokter dokter.wav --pasien pasien.wav [--approve --submit]

Hanya pakai audio SIMULASI. Tidak mencetak isi transkrip kecuali --show-text."""
import argparse
import json
import os
import sys
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dokter")
    ap.add_argument("--pasien")
    ap.add_argument("--mixed")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--show-text", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    base = os.environ.get("BASE_URL", "http://localhost:8000") + "/v1"
    c = httpx.Client(timeout=120)
    r = c.post(f"{base}/auth/login", json={"client": os.environ["MV_CLIENT"], "username": os.environ["MV_USER"],
                                           "password": os.environ["MV_PASSWORD"]})
    r.raise_for_status()
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    sid = c.post(f"{base}/sessions", headers=h, json={
        "no_rawat": "SMOKE/0001", "consent": {"given": True, "recorded_by": "smoke-test"}}).json()["id"]
    files = {k: (os.path.basename(p), open(p, "rb")) for k, p in
             (("dokter", a.dokter), ("pasien", a.pasien), ("mixed", a.mixed)) if p}
    c.post(f"{base}/sessions/{sid}/audio", headers=h, files=files).raise_for_status()
    t0 = time.time()
    c.post(f"{base}/sessions/{sid}/finish", headers=h).raise_for_status()
    while True:
        s = c.get(f"{base}/sessions/{sid}", headers=h).json()
        print(f"[{time.time() - t0:6.1f}s] {s['status']}  " + " ".join(f"{j['kind']}={j['status']}" for j in s["jobs"]))
        if s["status"] != "processing":
            break
        if time.time() - t0 > a.timeout:
            print("TIMEOUT")
            return 1
        time.sleep(4)
    rv = c.get(f"{base}/sessions/{sid}/review", headers=h).json()
    print("notices:", rv["notices"], " job_errors:", {k: v for k, v in rv["job_errors"].items() if v})
    print("segmen transkrip:", len(rv["transcript"]["segments"]))
    if a.show_text:
        for sg in rv["transcript"]["segments"]:
            print(f"  [{sg['idx']}] {sg['speaker']}: {sg['text']}")
    for it in rv["items"]:
        print(f"  {it['verdict']:9} {it['field']:18} {it['status']:18} {it['teks']!r} {it['reasons']}")
    for c in rv.get("codes", []):
        it = next((i for i in rv["items"] if i["id"] == c["item_id"]), {})
        print(f"  KODE {c['system']:6} {c['state']:8} {it.get('teks', '')!r} -> {c['suggested_code']} {c['suggested_display'] or ''} ({c['reason'] or 'ok'})")
    print("terlewat:", [(m['kind'], m['mention']) for m in rv["missed"]])
    if rv["soap"]:
        for s in rv["soap"]["sentences"]:
            print(f"  SOAP {s['section']}: {s['text']}{'  [DITANDAI]' if s['flagged'] else ''}")
    if a.approve and rv["soap"]:
        saved = c.put(f"{base}/sessions/{sid}/soap", headers=h, json={"sentences": [
            {"id": x["id"], "section": x["section"], "text": x["text"]} for x in rv["soap"]["sentences"]]}).json()
        r = c.post(f"{base}/sessions/{sid}/approve", headers=h, json={"soap_id": saved["id"], "acknowledge_flagged": True})
        print("approve:", r.status_code)
        if a.submit:
            print("submit:", c.post(f"{base}/sessions/{sid}/submit", headers=h).json())
    print("session:", sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
