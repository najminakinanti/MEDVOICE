"""Endpoint pendukung UI: profil, antrean (adapter mock), riwayat sesi."""
from sqlalchemy import text

from tests.conftest import login


def _mk(client, h, no_rawat):
    r = client.post("/v1/sessions", headers=h, json={"no_rawat": no_rawat, "consent": {"given": True, "recorded_by": "t"}})
    assert r.status_code == 201
    return r.json()["id"]


def test_me_hanya_dokter(client, tenant):
    h = login(client, tenant)
    assert client.get("/v1/me", headers=h).json()["username"] == "dr_a"
    assert client.get("/v1/me", headers={"X-API-Key": tenant["key"]}).status_code == 403
    assert client.get("/v1/me").status_code == 401


def test_antrean_dan_status_sesi(client, tenant):
    h = login(client, tenant)
    q = client.get("/v1/queue", headers=h).json()
    assert q["supported"] and q["unit"] == "Poli Umum" and len(q["items"]) == 7
    assert {i["state"] for i in q["items"]} == {"menunggu", "belum_hadir"}
    sid = _mk(client, h, q["items"][1]["no_rawat"])
    q2 = client.get("/v1/queue", headers=h).json()
    it = q2["items"][1]
    assert it["state"] == "diperiksa" and it["session"] == {"id": sid, "status": "recording"}
    assert q2["stats"]["today"] == 7 and q2["stats"]["done"] == 0
    assert client.get("/v1/queue", headers=login(client, tenant, "dr_b")).json()["items"][1]["session"] is None


def test_detail_sesi_memuat_pasien(client, tenant):
    h = login(client, tenant)
    sid = _mk(client, h, "2026/10/23/0002")
    s = client.get(f"/v1/sessions/{sid}", headers=h).json()
    assert s["patient"]["name"] == "Siti Rahmawati" and s["started_at"] and s["finished_at"] is None
    sid2 = _mk(client, h, "MANUAL/1")
    assert client.get(f"/v1/sessions/{sid2}", headers=h).json()["patient"] is None      # tanpa data SIMRS: tetap jalan


def test_riwayat_filter_cari_dan_paginasi(client, tenant):
    h = login(client, tenant)
    ids = [_mk(client, h, f"2026/10/23/000{n}") for n in (1, 2, 3)]
    from app.db import engine
    with engine().begin() as c:
        c.execute(text("UPDATE consult_sessions SET status='submitted', finished_at=started_at + interval '4 minutes' WHERE id=:i"),
                  dict(i=ids[1]))
    r = client.get("/v1/sessions", headers=h).json()
    assert r["total"] == 3 and r["items"][0]["id"] == ids[2]                # terbaru dulu
    assert client.get("/v1/sessions?status=submitted", headers=h).json()["items"][0]["duration_s"] == 240
    assert [i["id"] for i in client.get("/v1/sessions?q=siti", headers=h).json()["items"]] == [ids[1]]
    assert len(client.get("/v1/sessions?limit=2&offset=2", headers=h).json()["items"]) == 1
    assert client.get("/v1/sessions?status=ngawur", headers=h).status_code == 422
    assert client.get("/v1/sessions", headers=login(client, tenant, "dr_b")).json()["total"] == 0
