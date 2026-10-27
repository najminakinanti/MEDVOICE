"""Peran superadmin: kelola RS dan penggunanya; tanpa akses data klinis; aturan peran dijaga aplikasi DAN database."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import admin_api, security
from app.db import engine
from tests.conftest import login

PW = "passwordku-123"


@pytest.fixture(autouse=True)
def no_network_probes(monkeypatch):
    monkeypatch.setattr(admin_api, "_probe_stt", lambda: {"reachable": False})
    monkeypatch.setattr(admin_api, "_probe_llm", lambda: {"backend": "ollama", "model": "fake", "reachable": False, "installed": None})


def platform_id() -> str:
    with engine().begin() as c:
        return str(c.execute(text("SELECT id FROM clients WHERE is_platform")).scalar())


def make_superadmin() -> str:
    tag = uuid.uuid4().hex[:8]
    with engine().begin() as c:
        c.execute(text("INSERT INTO users(client_id, simrs_user_id, username, password_hash, display_name, email, role) "
                       "VALUES (:c,:u,:u,:p,:u,:e,'superadmin')"),
                  dict(c=platform_id(), u="sa_" + tag, p=security.hash_password(PW), e=f"sa.{tag}@platform.test"))
    return f"sa.{tag}@platform.test"


@pytest.fixture()
def sa(client):
    r = client.post("/v1/auth/login", json={"username": make_superadmin(), "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def new_hospital(client, sa, **kw):
    tag = uuid.uuid4().hex[:8]
    body = {"name": f"rs-uji-{tag}", "admin": {"display_name": "Admin " + tag, "email": f"admin.{tag}@rsuji.test"}, **kw}
    return client.post("/v1/platform/hospitals", json=body, headers=sa), body


# ---------------------------------------------------------------- hak akses
def test_hanya_superadmin_boleh_api_platform(client, tenant):
    admin_only = login(client, tenant, "dr_a")
    with engine().begin() as c:
        c.execute(text("UPDATE users SET role='admin' WHERE id=:i"), dict(i=tenant["doctors"]["dr_a"]))
    for who in (login(client, tenant, "dr_b"), admin_only):                  # dokter biasa dan admin RS
        assert client.get("/v1/platform/hospitals", headers=who).status_code == 403
        assert client.post("/v1/platform/hospitals", json={}, headers=who).status_code in (403, 422)
    assert client.get("/v1/platform/hospitals", headers={"X-API-Key": tenant["key"]}).status_code == 403
    assert client.get("/v1/platform/hospitals").status_code == 401


def test_superadmin_melihat_semua_menu_di_client_platform_miliknya(client, sa):
    # semua menu: alur klinis + halaman admin, semuanya pada client platform si superadmin sendiri
    assert client.get("/v1/queue", headers=sa).status_code == 200
    assert client.get("/v1/sessions", headers=sa).status_code == 200
    r = client.post("/v1/sessions", json={"no_rawat": "R-SA", "consent": {"given": True, "recorded_by": "x"}}, headers=sa)
    assert r.status_code == 201
    for path in ("/v1/admin/integration", "/v1/admin/settings", "/v1/admin/users", "/v1/platform/hospitals"):
        assert client.get(path, headers=sa).status_code == 200, path
    assert client.get("/v1/me", headers=sa).json()["role"] == "superadmin"


def test_superadmin_tidak_bisa_membaca_sesi_klinis_rs_lain_dan_sebaliknya(client, tenant, sa):
    mine = client.post("/v1/sessions", json={"no_rawat": "R-SA2", "consent": {"given": True, "recorded_by": "x"}}, headers=sa).json()["id"]
    dr = login(client, tenant, "dr_a")
    theirs = client.post("/v1/sessions", json={"no_rawat": "R-DR", "consent": {"given": True, "recorded_by": "x"}}, headers=dr).json()["id"]
    assert client.get(f"/v1/sessions/{theirs}", headers=sa).status_code == 404          # superadmin tak bisa membuka sesi dokter RS
    assert client.get(f"/v1/sessions/{mine}", headers=dr).status_code == 404            # dan dokter RS tak bisa membuka sesi superadmin
    assert theirs not in {x["id"] for x in client.get("/v1/sessions", headers=sa).json()["items"]}
    assert client.get(f"/v1/sessions/{mine}", headers=sa).status_code == 200


# ---------------------------------------------------------------- rumah sakit
def test_buat_rumah_sakit_beserta_admin_pertama(client, sa):
    r, body = new_hospital(client, sa)
    assert r.status_code == 201, r.text
    temp = r.json()["admin"]["temporary_password"]
    ok = client.post("/v1/auth/login", json={"username": body["admin"]["email"], "password": temp})
    assert ok.status_code == 200                                              # admin pertama bisa langsung masuk, tanpa memilih RS
    me = client.get("/v1/me", headers={"Authorization": "Bearer " + ok.json()["access_token"]}).json()
    assert (me["role"], me["client"]) == ("admin", body["name"])
    h = next(h for h in client.get("/v1/platform/hospitals", headers=sa).json()["items"] if h["name"] == body["name"])
    assert (h["active"], h["active_users"], h["active_admins"], h["rate_limit_per_min"]) == (True, 1, 1, 60)
    with engine().begin() as c:                                               # tercatat pada RS yang terdampak
        assert c.execute(text("SELECT count(*) FROM audit_log WHERE client_id=:c AND action='platform.hospital_created'"), dict(c=h["id"])).scalar() == 1


def test_buat_rumah_sakit_validasi_dan_atomik(client, sa):
    ada = lambda name: any(h["name"] == name for h in client.get("/v1/platform/hospitals", headers=sa).json()["items"])  # noqa: E731
    for bad in ("RS Besar", "ab", "-awal", "rs_garis_bawah", "x" * 61):
        r, _ = new_hospital(client, sa, name=bad)
        assert r.status_code == 422, bad
    r, body = new_hospital(client, sa)
    assert r.status_code == 201
    again = client.post("/v1/platform/hospitals", json={**body, "admin": {"display_name": "B", "email": "lain@rsuji.test"}}, headers=sa)
    assert again.status_code == 409 and again.json()["detail"] == "hospital_name_taken"
    # admin pertama tak valid -> RS TIDAK boleh terbentuk setengah jadi
    tag = uuid.uuid4().hex[:8]
    half = client.post("/v1/platform/hospitals", json={"name": "rs-setengah-" + tag, "admin": {"display_name": "X", "email": "bukan-email"}}, headers=sa)
    assert half.status_code == 422 and not ada("rs-setengah-" + tag)
    dup = client.post("/v1/platform/hospitals", json={"name": "rs-dupemail-" + tag, "admin": {"display_name": "Y", "email": body["admin"]["email"]}}, headers=sa)
    assert dup.status_code == 409 and not ada("rs-dupemail-" + tag)           # email sudah dipakai RS lain: batal total
    assert client.post("/v1/platform/hospitals", json={"name": "rs-x-" + tag}, headers=sa).status_code == 422   # admin wajib


def test_nonaktifkan_rumah_sakit_mengunci_semua_penggunanya(client, sa):
    r, body = new_hospital(client, sa)
    hid, temp = r.json()["id"], r.json()["admin"]["temporary_password"]
    cred = {"username": body["admin"]["email"], "password": temp}
    assert client.post("/v1/auth/login", json=cred).status_code == 200
    assert client.put(f"/v1/platform/hospitals/{hid}", json={"active": False}, headers=sa).status_code == 200
    assert client.post("/v1/auth/login", json=cred).status_code == 401
    assert client.put(f"/v1/platform/hospitals/{hid}", json={"active": True}, headers=sa).status_code == 200
    assert client.post("/v1/auth/login", json=cred).status_code == 200


def test_atur_batas_rumah_sakit(client, sa):
    hid = new_hospital(client, sa)[0].json()["id"]
    put = lambda **b: client.put(f"/v1/platform/hospitals/{hid}", json=b, headers=sa)  # noqa: E731
    assert put(rate_limit_per_min=0).status_code == 422 and put(monthly_quota=0).status_code == 422
    assert put(rate_limit_per_min=120, monthly_quota=500).status_code == 200
    get = lambda: next(h for h in client.get("/v1/platform/hospitals", headers=sa).json()["items"] if h["id"] == hid)  # noqa: E731
    assert (get()["rate_limit_per_min"], get()["monthly_quota"]) == (120, 500)
    assert put(monthly_quota=None).status_code == 200 and get()["monthly_quota"] is None      # null = tanpa kuota
    assert get()["rate_limit_per_min"] == 120                                                 # tak berubah bila tak dikirim


def test_client_platform_bukan_rumah_sakit(client, sa):
    pid = platform_id()
    assert pid not in {h["id"] for h in client.get("/v1/platform/hospitals", headers=sa).json()["items"]}
    assert client.put(f"/v1/platform/hospitals/{pid}", json={"active": False}, headers=sa).status_code == 404
    assert client.get(f"/v1/platform/hospitals/{pid}/users", headers=sa).status_code == 404
    assert client.get("/v1/platform/hospitals/bukan-uuid/users", headers=sa).status_code == 404


# ---------------------------------------------------------------- pengguna RS oleh superadmin
def test_kelola_pengguna_rs_mana_pun(client, sa):
    r, body = new_hospital(client, sa)
    hid = r.json()["id"]
    lst = client.get(f"/v1/platform/hospitals/{hid}/users", headers=sa).json()
    assert lst["roles"] == ["dokter", "admin"] and lst["hospital"]["name"] == body["name"] and lst["total"] == 1
    mk = client.post(f"/v1/platform/hospitals/{hid}/users", json={"display_name": "dr. Baru", "email": f"baru.{uuid.uuid4().hex[:6]}@rsuji.test"}, headers=sa)
    assert mk.status_code == 201
    uid = mk.json()["id"]
    assert client.put(f"/v1/platform/hospitals/{hid}/users/{uid}", json={"role": "admin"}, headers=sa).status_code == 200
    assert client.put(f"/v1/platform/hospitals/{hid}/users/{uid}", json={"role": "superadmin"}, headers=sa).json()["detail"] == "role_invalid"
    assert "temporary_password" in client.post(f"/v1/platform/hospitals/{hid}/users/{uid}/reset-password", json={}, headers=sa).json()
    # pengguna RS lain tidak bisa dijangkau lewat RS ini
    other = new_hospital(client, sa)[0].json()["id"]
    assert client.put(f"/v1/platform/hospitals/{other}/users/{uid}", json={"active": False}, headers=sa).status_code == 404
    with engine().begin() as c:
        assert c.execute(text("SELECT count(*) FROM audit_log WHERE client_id=:c AND action LIKE 'admin.%'"), dict(c=hid)).scalar() >= 3


# ---------------------------------------------------------------- aturan peran
def test_superadmin_hanya_di_client_platform_dijaga_db(client, tenant, sa):
    # lewat API: RS tak bisa diberi peran superadmin; platform tak bisa diberi peran admin/dokter
    h = new_hospital(client, sa)[0].json()["id"]
    assert client.post(f"/v1/platform/hospitals/{h}/users", json={"display_name": "x", "email": "x@rsuji.test", "role": "superadmin"}, headers=sa).status_code == 422
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "y@platform.test", "role": "admin"}, headers=sa).status_code == 422
    assert client.get("/v1/admin/users", headers=sa).json()["roles"] == ["superadmin"]
    # langsung ke database (melewati aplikasi): trigger menolak
    with pytest.raises(IntegrityError):
        with engine().begin() as c:
            c.execute(text("UPDATE users SET role='superadmin' WHERE id=:i"), dict(i=tenant["doctors"]["dr_a"]))
    with pytest.raises(IntegrityError):
        with engine().begin() as c:
            c.execute(text("INSERT INTO users(client_id, simrs_user_id, username, display_name, role) VALUES (:c,'z','z','z','dokter')"), dict(c=platform_id()))


def test_kelola_sesama_superadmin_dan_pelindung_diri_sendiri(client, sa):
    r = client.post("/v1/admin/users", json={"display_name": "SA Dua", "email": f"sa2.{uuid.uuid4().hex[:6]}@platform.test"}, headers=sa)
    assert r.status_code == 201 and "temporary_password" in r.json()           # peran bawaan di platform = superadmin
    listing = client.get("/v1/admin/users", headers=sa).json()["items"]
    me = next(u for u in listing if u["is_self"])
    assert client.put(f"/v1/admin/users/{me['id']}", json={"active": False}, headers=sa).json()["detail"] == "cannot_modify_self"
    assert client.put(f"/v1/admin/users/{r.json()['id']}", json={"active": False}, headers=sa).status_code == 200


def test_admin_rs_tidak_bisa_menaikkan_diri_sendiri_menjadi_superadmin_atau_mengubah_peran_sendiri(client, tenant):
    with engine().begin() as c:
        c.execute(text("UPDATE users SET role='admin' WHERE id=:i"), dict(i=tenant["doctors"]["dr_a"]))
    h = login(client, tenant, "dr_a")
    me = str(tenant["doctors"]["dr_a"])
    assert client.put(f"/v1/admin/users/{me}", json={"role": "superadmin"}, headers=h).status_code == 422
    assert client.put(f"/v1/admin/users/{me}", json={"role": "dokter"}, headers=h).json()["detail"] == "cannot_modify_self"


def test_sistem_memuat_status_teknis_untuk_superadmin(client, sa):
    d = client.get("/v1/platform/system", headers=sa).json()
    assert d["stt"] == {"reachable": False} and d["llm"]["backend"] == "ollama"
    assert {"gpu_timeshare", "embedding_model", "max_audio_mb", "terminology", "default_retention_days", "default_session_minutes"} <= set(d)
    from app.config import get_settings
    blob = str(d).lower()
    for name in ("jwt_secret", "api_key_pepper", "database_url"):
        assert str(getattr(get_settings(), name)).lower() not in blob
