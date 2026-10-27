"""API admin RS: pengguna, integrasi SIMRS, pengaturan. Fokus: hak akses, isolasi antar-RS, dan keunikan."""
import uuid

import pytest
from sqlalchemy import text

from app import admin_api, security
from app.db import engine
from tests.conftest import login

PW = "passwordku-123"


def make_admin(tenant, user="dr_a"):
    with engine().begin() as c:
        c.execute(text("UPDATE users SET role='admin' WHERE id=:i"), dict(i=tenant["doctors"][user]))


def other_tenant():
    """RS kedua dengan satu admin, untuk uji isolasi."""
    tag = uuid.uuid4().hex[:8]
    with engine().begin() as c:
        cid = c.execute(text("INSERT INTO clients(name) VALUES (:n) RETURNING id"), dict(n="rs-lain-" + tag)).scalar()
        uid = c.execute(text(
            "INSERT INTO users(client_id, simrs_user_id, username, password_hash, display_name, email, role) "
            "VALUES (:c,:u,:u,:p,:u,:e,'admin') RETURNING id"),
            dict(c=cid, u="adm_" + tag, p=security.hash_password(PW), e=f"adm.{tag}@lain.test")).scalar()
        key, prefix, h = security.new_api_key()
        c.execute(text("INSERT INTO api_keys(client_id, key_prefix, key_hash, label) VALUES (:c,:p,:h,'lain')"), dict(c=cid, p=prefix, h=h))
    return {"cid": str(cid), "uid": str(uid), "email": f"adm.{tag}@lain.test", "prefix": prefix}


@pytest.fixture()
def admin(client, tenant):
    make_admin(tenant)
    return login(client, tenant, "dr_a")


@pytest.fixture(autouse=True)
def no_network_probes(monkeypatch):
    monkeypatch.setattr(admin_api, "_probe_stt", lambda: {"reachable": False})
    monkeypatch.setattr(admin_api, "_probe_llm", lambda: {"backend": "ollama", "model": "fake", "reachable": False, "installed": None})


def new_user(client, h, **kw):
    tag = uuid.uuid4().hex[:8]
    body = {"display_name": "dr. Baru " + tag, "email": f"baru.{tag}@rs.test", **kw}
    return client.post("/v1/admin/users", json=body, headers=h), body


# ---------------------------------------------------------------- hak akses
ADMIN_GETS = ["/v1/admin/users", "/v1/admin/integration", "/v1/admin/integration/webhook-secret", "/v1/admin/settings"]


def test_dokter_biasa_tidak_boleh_masuk_api_admin(client, tenant):
    h = login(client, tenant, "dr_b")                                  # role 'dokter'
    for path in ADMIN_GETS:
        assert client.get(path, headers=h).status_code == 403, path
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "x@rs.test"}, headers=h).status_code == 403
    assert client.post("/v1/admin/settings/purge", headers=h).status_code == 403
    assert client.post("/v1/admin/integration/keys", json={"label": "x"}, headers=h).status_code == 403


def test_tanpa_login_dan_api_key_ditolak(client, tenant):
    assert client.get("/v1/admin/users").status_code == 401
    assert client.get("/v1/admin/users", headers={"X-API-Key": tenant["key"]}).status_code == 403   # kunci SIMRS bukan admin


def test_me_menyertakan_peran(client, tenant, admin):
    assert client.get("/v1/me", headers=admin).json()["role"] == "admin"
    assert client.get("/v1/me", headers=login(client, tenant, "dr_b")).json()["role"] == "dokter"


# ---------------------------------------------------------------- pengguna
def test_daftar_hanya_pengguna_rs_sendiri(client, tenant, admin):
    lain = other_tenant()
    items = client.get("/v1/admin/users", headers=admin).json()["items"]
    assert {u["username"] for u in items} == {"dr_a", "dr_b"}
    assert all(lain["email"] != u["email"] for u in items)
    assert [u["is_self"] for u in items if u["username"] == "dr_a"] == [True]


def test_buat_pengguna_kata_sandi_acak_lalu_bisa_login_dengan_email(client, tenant, admin):
    r, body = new_user(client, admin)
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    assert len(temp) >= 10
    ok = client.post("/v1/auth/login", json={"username": body["email"].upper(), "password": temp})
    assert ok.status_code == 200
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + ok.json()["access_token"]}).json()["client"] == tenant["name"]


def test_buat_pengguna_validasi_dan_keunikan(client, tenant, admin):
    assert client.post("/v1/admin/users", json={"display_name": "x"}, headers=admin).status_code == 422                  # tanpa email/NIP
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "bukan-email"}, headers=admin).status_code == 422
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "x@rs.test", "password": "pendek"}, headers=admin).status_code == 422
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "x@rs.test", "role": "root"}, headers=admin).status_code == 422
    tag = uuid.uuid4().hex[:8]
    first = {"display_name": "A", "email": f"dup.{tag}@rs.test", "nip": "N" + tag, "username": "u_" + tag, "password": "kata-sandi-panjang"}
    assert client.post("/v1/admin/users", json=first, headers=admin).status_code == 201
    for field, code in (("email", "email_taken"), ("nip", "nip_taken"), ("username", "username_taken")):
        again = {"display_name": "B", "email": f"b.{uuid.uuid4().hex[:6]}@rs.test", "nip": "M" + uuid.uuid4().hex[:6],
                 "username": "v_" + uuid.uuid4().hex[:6], "password": "kata-sandi-panjang"}
        again[field] = first[field].upper() if field == "email" else first[field]
        r = client.post("/v1/admin/users", json=again, headers=admin)
        assert r.status_code == 409 and r.json()["detail"] == code, (field, r.text)
    # setelah konflik, transaksi tetap sehat (savepoint): daftar masih bisa dibaca
    assert client.get("/v1/admin/users", headers=admin).status_code == 200


def test_ubah_pengguna_nonaktif_tidak_bisa_login_lagi(client, tenant, admin):
    r, body = new_user(client, admin, password="kata-sandi-panjang")
    uid = r.json()["id"]
    assert client.post("/v1/auth/login", json={"username": body["email"], "password": "kata-sandi-panjang"}).status_code == 200
    assert client.put(f"/v1/admin/users/{uid}", json={"active": False}, headers=admin).status_code == 200
    assert client.post("/v1/auth/login", json={"username": body["email"], "password": "kata-sandi-panjang"}).status_code == 401
    assert client.put(f"/v1/admin/users/{uid}", json={"active": True, "role": "admin", "display_name": "Dr. Ganti"}, headers=admin).status_code == 200
    u = next(u for u in client.get("/v1/admin/users", headers=admin).json()["items"] if u["id"] == uid)
    assert (u["active"], u["role"], u["display_name"]) == (True, "admin", "Dr. Ganti")


def test_tidak_boleh_menurunkan_atau_menonaktifkan_diri_sendiri(client, tenant, admin):
    me = str(tenant["doctors"]["dr_a"])
    assert client.put(f"/v1/admin/users/{me}", json={"active": False}, headers=admin).json()["detail"] == "cannot_modify_self"
    assert client.put(f"/v1/admin/users/{me}", json={"role": "dokter"}, headers=admin).json()["detail"] == "cannot_modify_self"
    assert client.put(f"/v1/admin/users/{me}", json={"display_name": "Nama Baru"}, headers=admin).status_code == 200   # ubah nama tetap boleh


def test_identitas_tidak_boleh_dikosongkan_keduanya(client, tenant, admin):
    r, _ = new_user(client, admin)
    assert client.put(f"/v1/admin/users/{r.json()['id']}", json={"email": None}, headers=admin).json()["detail"] == "identity_required"


def test_pengguna_rs_lain_tidak_terlihat_dan_tidak_bisa_diubah(client, tenant, admin):
    lain = other_tenant()
    for call in (lambda: client.put(f"/v1/admin/users/{lain['uid']}", json={"active": False}, headers=admin),
                 lambda: client.post(f"/v1/admin/users/{lain['uid']}/reset-password", json={}, headers=admin)):
        assert call().status_code == 404
    assert client.put("/v1/admin/users/bukan-uuid", json={}, headers=admin).status_code == 404
    with engine().begin() as c:
        assert c.execute(text("SELECT active FROM users WHERE id=:i"), dict(i=lain["uid"])).scalar() is True


def test_reset_kata_sandi_orang_lain_bukan_diri_sendiri(client, tenant, admin):
    r, body = new_user(client, admin, password="kata-sandi-lama1")
    uid = r.json()["id"]
    assert client.post(f"/v1/admin/users/{uid}/reset-password", json={"password": "pendek"}, headers=admin).status_code == 422
    temp = client.post(f"/v1/admin/users/{uid}/reset-password", json={}, headers=admin).json()["temporary_password"]
    assert client.post("/v1/auth/login", json={"username": body["email"], "password": "kata-sandi-lama1"}).status_code == 401
    assert client.post("/v1/auth/login", json={"username": body["email"], "password": temp}).status_code == 200
    me = str(tenant["doctors"]["dr_a"])
    assert client.post(f"/v1/admin/users/{me}/reset-password", json={}, headers=admin).json()["detail"] == "use_profile"


def test_perubahan_admin_tercatat_di_audit_tanpa_rahasia(client, tenant, admin):
    r, body = new_user(client, admin, password="rahasia-sekali-pakai")
    client.post(f"/v1/admin/users/{r.json()['id']}/reset-password", json={"password": "rahasia-lain-12345"}, headers=admin)
    with engine().begin() as c:
        rows = c.execute(text("SELECT action, before::text, after::text FROM audit_log WHERE client_id=:c AND action LIKE 'admin.%'"),
                         dict(c=tenant["id"])).all()
    assert {"admin.user_created", "admin.password_reset"} <= {r[0] for r in rows}
    blob = " ".join(" ".join(str(x) for x in r) for r in rows)
    assert "rahasia-sekali-pakai" not in blob and "rahasia-lain-12345" not in blob


# ---------------------------------------------------------------- profil sendiri
def test_ganti_kata_sandi_sendiri(client, tenant):
    h = login(client, tenant, "dr_b")
    url = "/v1/me/password"
    assert client.post(url, json={"current_password": "salah-salah-1", "new_password": "baru-baru-baru1"}, headers=h).json()["detail"] == "current_password_wrong"
    assert client.post(url, json={"current_password": PW, "new_password": "pendek"}, headers=h).json()["detail"] == "password_too_short"
    assert client.post(url, json={"current_password": PW, "new_password": PW}, headers=h).json()["detail"] == "password_unchanged"
    assert client.post(url, json={"current_password": PW, "new_password": "baru-baru-baru1"}, headers=h).status_code == 200
    assert client.post("/v1/auth/login", json={"client": tenant["name"], "username": "dr_b", "password": PW}).status_code == 401
    assert client.post("/v1/auth/login", json={"client": tenant["name"], "username": "dr_b", "password": "baru-baru-baru1"}).status_code == 200
    assert client.post(url, json={"current_password": "x", "new_password": "y" * 12}).status_code == 401           # tanpa login


# ---------------------------------------------------------------- integrasi SIMRS
def test_integrasi_ringkasan_dan_kunci_api(client, tenant, admin):
    d = client.get("/v1/admin/integration", headers=admin).json()
    assert d["adapter"] == "mock" and "mock" in d["adapters"] and {k["prefix"] for k in d["keys"]} == {tenant["key"][:8]}
    made = client.post("/v1/admin/integration/keys", json={"label": "simrs-utama"}, headers=admin).json()
    assert made["key"].startswith("mvk_") and made["key"][:8] == made["prefix"]
    # kunci baru benar-benar bekerja pada API, dan utuhnya TIDAK muncul lagi di daftar
    assert client.get("/v1/sessions", headers={"X-API-Key": made["key"]}).status_code in (200, 403)
    listing = client.get("/v1/admin/integration", headers=admin).json()
    assert made["key"] not in str(listing) and made["prefix"] in {k["prefix"] for k in listing["keys"]}
    assert client.post(f"/v1/admin/integration/keys/{made['prefix']}/revoke", headers=admin).status_code == 200
    assert client.post(f"/v1/admin/integration/keys/{made['prefix']}/revoke", headers=admin).status_code == 404       # sudah dicabut
    assert client.post("/v1/admin/integration/keys", json={"label": ""}, headers=admin).status_code == 422


def test_kunci_rs_lain_tidak_bisa_dicabut_dan_tidak_terlihat(client, tenant, admin):
    lain = other_tenant()
    assert lain["prefix"] not in str(client.get("/v1/admin/integration", headers=admin).json())
    assert client.post(f"/v1/admin/integration/keys/{lain['prefix']}/revoke", headers=admin).status_code == 404
    with engine().begin() as c:
        assert c.execute(text("SELECT revoked_at FROM api_keys WHERE key_prefix=:p"), dict(p=lain["prefix"])).scalar() is None


def test_webhook_validasi_rahasia_dan_penghapusan(client, tenant, admin):
    for bad in ("ftp://x.test/h", "bukan url", "https://user:pw@x.test/h", "https:///tanpa-host"):
        assert client.put("/v1/admin/integration/webhook", json={"url": bad}, headers=admin).status_code == 422, bad
    assert client.put("/v1/admin/integration/webhook", json={"url": "https://simrs.rs.test/hook"}, headers=admin).status_code == 200
    assert client.get("/v1/admin/integration", headers=admin).json()["webhook_url"] == "https://simrs.rs.test/hook"
    assert client.get("/v1/admin/integration/webhook-secret", headers=admin).json()["secret"] == security.webhook_secret(tenant["id"])
    assert client.put("/v1/admin/integration/webhook", json={"url": None}, headers=admin).status_code == 200
    assert client.get("/v1/admin/integration", headers=admin).json()["webhook_url"] is None
    with engine().begin() as c:                                      # melihat rahasia tercatat, isi rahasianya tidak
        rows = c.execute(text("SELECT action, after::text FROM audit_log WHERE client_id=:c AND action LIKE 'admin.webhook%'"), dict(c=tenant["id"])).all()
    assert "admin.webhook_secret_viewed" in {r[0] for r in rows} and security.webhook_secret(tenant["id"]) not in str(rows)


def test_origin_dan_adapter(client, tenant, admin):
    for bad in ("https://x.test/path", "x.test", "ftp://x.test", "https://x.test?a=1"):
        assert client.put("/v1/admin/integration/origins", json={"origins": [bad]}, headers=admin).status_code == 422, bad
    ok = client.put("/v1/admin/integration/origins", json={"origins": ["https://web.rs.test", "https://web.rs.test", "http://localhost:5173"]}, headers=admin)
    assert ok.json()["allowed_origins"] == ["https://web.rs.test", "http://localhost:5173"]              # duplikat dibuang
    assert client.put("/v1/admin/integration/adapter", json={"adapter": "tidak-ada"}, headers=admin).status_code == 422
    assert client.put("/v1/admin/integration/adapter", json={"adapter": "mock"}, headers=admin).status_code == 200


def test_uji_koneksi_adapter_mock(client, tenant, admin):
    r = client.post("/v1/admin/integration/test", headers=admin).json()
    assert r["ok"] is True and r["adapter"] == "mock"


# ---------------------------------------------------------------- pengaturan
def test_pengaturan_rs_tidak_memuat_hal_teknis_server_dan_rahasia(client, tenant, admin):
    d = client.get("/v1/admin/settings", headers=admin).json()
    assert d["retention_days"] == 30 and d["limits"]["rate_limit_per_min"] > 0
    for teknis in ("stt", "llm", "terminology", "gpu_timeshare", "embedding_model", "max_audio_mb"):
        assert teknis not in d, teknis                                              # urusan pengelola platform, bukan admin RS
    blob = str(d).lower()
    for secret in (get_settings_secret("jwt_secret"), get_settings_secret("api_key_pepper"), get_settings_secret("database_url")):
        assert secret.lower() not in blob


def get_settings_secret(name):
    from app.config import get_settings
    return str(getattr(get_settings(), name))


def test_purge_hanya_transkrip_rs_sendiri(client, tenant, admin):
    lain = other_tenant()

    def expired_transcript(cid, uid):
        with engine().begin() as c:
            sid = c.execute(text("INSERT INTO consult_sessions(client_id, user_id, no_rawat, consent_at, consent_by) "
                                 "VALUES (:c,:u,:n,now(),'x') RETURNING id"), dict(c=cid, u=uid, n="R" + uuid.uuid4().hex[:6])).scalar()
            return c.execute(text("INSERT INTO transcripts(client_id, session_id, stt_model, language, is_empty, purge_after) "
                                  "VALUES (:c,:s,'m','id',false, now() - interval '1 day') RETURNING id"), dict(c=cid, s=sid)).scalar()
    mine = expired_transcript(tenant["id"], str(tenant["doctors"]["dr_a"]))
    theirs = expired_transcript(lain["cid"], lain["uid"])
    assert client.get("/v1/admin/settings", headers=admin).json()["transcripts"]["due_for_purge"] >= 1
    assert client.post("/v1/admin/settings/purge", headers=admin).json()["transcripts_purged"] >= 1
    with engine().begin() as c:
        purged = lambda t: c.execute(text("SELECT purged_at IS NOT NULL FROM transcripts WHERE id=:i"), dict(i=t)).scalar()  # noqa: E731
        assert purged(mine) is True and purged(theirs) is False        # transkrip RS lain tidak disentuh


# ---------------------------------------------------------------- tabel role & jabatan
def test_tabel_role_adalah_sumber_daftar_peran(client, tenant, admin):
    cat = {r["code"]: r for r in client.get("/v1/admin/settings", headers=admin).json()["roles"]}
    assert list(cat) == ["dokter", "admin", "superadmin"]                          # urut menurut rank
    assert (cat["dokter"]["scope"], cat["admin"]["scope"], cat["superadmin"]["scope"]) == ("hospital", "hospital", "platform")
    assert all(r["label"] and r["description"] for r in cat.values())
    d = client.get("/v1/admin/users", headers=admin).json()
    assert d["roles"] == ["dokter", "admin"] and d["role_labels"]["admin"] == "Admin RS"      # RS: hanya peran ber-scope hospital
    me = client.get("/v1/me", headers=admin).json()
    assert (me["role"], me["role_label"]) == ("admin", "Admin RS")


def test_peran_di_luar_tabel_role_ditolak_database(tenant):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):                                             # kunci asing ke roles
        with engine().begin() as c:
            c.execute(text("UPDATE users SET role='perawat' WHERE id=:i"), dict(i=tenant["doctors"]["dr_a"]))
    with pytest.raises(IntegrityError):                                             # tabel role tak boleh punya dua peran dengan rank sama
        with engine().begin() as c:
            c.execute(text("INSERT INTO roles(code,label,scope,rank) VALUES ('x','X','hospital',1)"))


def test_jabatan_dibuat_diubah_dan_dihapus(client, tenant, admin):
    r, body = new_user(client, admin, title="  Sp.PD  ")
    uid = r.json()["id"]
    get = lambda: next(u for u in client.get("/v1/admin/users", headers=admin).json()["items"] if u["id"] == uid)  # noqa: E731
    assert get()["title"] == "Sp.PD"                                                # spasi dirapikan
    assert client.put(f"/v1/admin/users/{uid}", json={"title": "Dokter Umum"}, headers=admin).status_code == 200
    assert get()["title"] == "Dokter Umum"
    assert client.put(f"/v1/admin/users/{uid}", json={"title": None}, headers=admin).status_code == 200
    assert get()["title"] is None                                                   # null = hapus
    assert client.put(f"/v1/admin/users/{uid}", json={"display_name": "Nama Baru"}, headers=admin).status_code == 200
    assert get()["title"] is None                                                   # tak dikirim = tak berubah
    assert client.post("/v1/admin/users", json={"display_name": "x", "email": "t@rs.test", "title": "x" * 81}, headers=admin).status_code == 422


def test_ringkasan_integrasi_memuat_data_pengiriman_nyata(client, tenant, admin):
    d = client.get("/v1/admin/integration", headers=admin).json()
    assert d["last_submission_at"] is None and d["last_success_at"] is None and d["failed_7d"] == 0
    cid, uid = tenant["id"], tenant["doctors"]["dr_a"]
    with engine().begin() as c:
        sid = c.execute(text("INSERT INTO consult_sessions(client_id, user_id, no_rawat, consent_at, consent_by) "
                             "VALUES (:c,:u,'RX',now(),'x') RETURNING id"), dict(c=cid, u=uid)).scalar()
        # database hanya mengizinkan pengiriman untuk SOAP yang sudah disetujui dokter, dan hanya versi dokter yang boleh disetujui
        soap = c.execute(text("INSERT INTO soap_notes(client_id, session_id, version, source, created_by, approved_by, approved_at) "
                              "VALUES (:c,:s,1,'dokter',:u,:u, now()) RETURNING id"), dict(c=cid, s=sid, u=uid)).scalar()
        for status, ago in (("succeeded", "1 hour"), ("failed", "2 days"), ("failed", "9 days")):   # 9 hari lalu: di luar jendela 7 hari
            c.execute(text("INSERT INTO simrs_submissions(client_id, session_id, soap_id, adapter, status, submitted_at) "
                           "VALUES (:c,:s,:n,'mock',:st, now() - CAST(:ago AS interval))"), dict(c=cid, s=sid, n=soap, st=status, ago=ago))
    d = client.get("/v1/admin/integration", headers=admin).json()
    assert d["last_submission_at"] and d["last_success_at"] and d["failed_7d"] == 1
    assert d["last_submission_at"] == d["last_success_at"]                          # yang terbaru adalah yang berhasil (1 jam lalu)


# ---------------------------------------------------------------- data & privasi, keamanan (per RS)
def _transcript(cid, uid, days_ago=0, purge_in_days=30):
    with engine().begin() as c:
        sid = c.execute(text("INSERT INTO consult_sessions(client_id, user_id, no_rawat, consent_at, consent_by) VALUES (:c,:u,:n,now(),'x') RETURNING id"),
                        dict(c=cid, u=uid, n="R" + uuid.uuid4().hex[:6])).scalar()
        return c.execute(text("INSERT INTO transcripts(client_id, session_id, stt_model, language, is_empty, created_at, purge_after) "
                              "VALUES (:c,:s,'m','id',false, now() - make_interval(days => :a), now() + make_interval(days => :p)) RETURNING id"),
                         dict(c=cid, s=sid, a=days_ago, p=purge_in_days)).scalar()


def _days_left(t):
    with engine().connect() as c:
        return c.execute(text("SELECT round(extract(epoch FROM (purge_after - created_at))/86400) FROM transcripts WHERE id=:i"), dict(i=t)).scalar()


def test_retensi_per_rs_berlaku_juga_untuk_transkrip_tersimpan(client, tenant, admin):
    lain = other_tenant()
    mine = _transcript(tenant["id"], str(tenant["doctors"]["dr_a"]), days_ago=2)
    theirs = _transcript(lain["cid"], lain["uid"], days_ago=2)
    theirs_before = _days_left(theirs)                                              # 32: dibuat 2 hari lalu, purge 30 hari ke depan
    assert client.put("/v1/admin/settings/privacy", json={"retention_days": 0}, headers=admin).status_code == 422
    assert client.put("/v1/admin/settings/privacy", json={"retention_days": 366}, headers=admin).status_code == 422
    r = client.put("/v1/admin/settings/privacy", json={"retention_days": 7}, headers=admin)
    assert r.status_code == 200 and r.json()["transcripts_recalculated"] >= 1
    assert _days_left(mine) == 7 and _days_left(theirs) == theirs_before == 32     # RS lain tidak tersentuh
    pr = client.get("/v1/admin/settings", headers=admin).json()
    assert (pr["retention_days"], pr["privacy"]["retention_custom"], pr["privacy"]["retention_default"]) == (7, 7, 30)
    assert client.put("/v1/admin/settings/privacy", json={"retention_days": None}, headers=admin).status_code == 200
    assert client.get("/v1/admin/settings", headers=admin).json()["retention_days"] == 30 and _days_left(mine) == 30   # null = bawaan server


def test_teks_consent_per_rs_tampil_di_me_dan_bisa_dikembalikan(client, tenant, admin):
    assert client.get("/v1/me", headers=admin).json()["consent_text"] is None
    assert client.put("/v1/admin/settings/privacy", json={"consent_text": "x" * 2001}, headers=admin).status_code == 422
    assert client.put("/v1/admin/settings/privacy", json={"consent_text": "  Rekaman dipakai untuk catatan medis RS ini.  "}, headers=admin).status_code == 200
    assert client.get("/v1/me", headers=admin).json()["consent_text"] == "Rekaman dipakai untuk catatan medis RS ini."
    dokter = login(client, tenant, "dr_b")                                          # dokter di RS yang sama juga melihatnya
    assert client.get("/v1/me", headers=dokter).json()["consent_text"] == "Rekaman dipakai untuk catatan medis RS ini."
    assert client.put("/v1/admin/settings/privacy", json={"consent_text": "   "}, headers=admin).status_code == 200
    assert client.get("/v1/me", headers=admin).json()["consent_text"] is None       # kosong = kembali ke teks bawaan


def test_masa_sesi_login_per_rs(client, tenant, admin):
    cred = {"client": tenant["name"], "username": "dr_b", "password": "passwordku-123"}
    assert client.post("/v1/auth/login", json=cred).json()["expires_in"] == 480 * 60
    for bad in (5, 14, 1441):
        assert client.put("/v1/admin/settings/security", json={"session_minutes": bad}, headers=admin).status_code == 422, bad
    assert client.put("/v1/admin/settings/security", json={"session_minutes": 30}, headers=admin).status_code == 200
    r = client.post("/v1/auth/login", json=cred).json()
    assert r["expires_in"] == 1800
    import jwt as pyjwt
    claims = pyjwt.decode(r["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 1800                                    # token benar-benar berumur 30 menit
    assert client.put("/v1/admin/settings/security", json={"session_minutes": None}, headers=admin).status_code == 200
    assert client.post("/v1/auth/login", json=cred).json()["expires_in"] == 480 * 60


# ---------------------------------------------------------------- log audit
def test_log_audit_hanya_rs_sendiri_dengan_filter_dan_gagal_login_tercatat(client, tenant, admin):
    lain = other_tenant()
    client.post("/v1/auth/login", json={"username": lain["email"], "password": "salah-salah-1"})                      # gagal di RS lain
    client.post("/v1/auth/login", json={"client": tenant["name"], "username": "dr_b", "password": "salah-salah-1"})   # gagal di RS ini
    new_user(client, admin)                                                          # tindakan admin
    d = client.get("/v1/admin/audit?limit=200", headers=admin).json()
    assert d["total"] >= 3 and all(i["label"] for i in d["items"])
    assert "Gagal masuk (kata sandi/akun salah)" in {i["label"] for i in d["items"]}                 # login gagal akun RS ini terlihat
    assert lain["email"] not in str(d)                                                               # RS lain tidak bocor
    adm = client.get("/v1/admin/audit?group=admin", headers=admin).json()["items"]
    assert adm and all(i["action"].startswith(("admin.", "platform.", "user.")) for i in adm)
    assert any(i["action"] == "admin.user_created" for i in adm)
    log = client.get("/v1/admin/audit?group=login", headers=admin).json()["items"]
    assert log and all(i["action"].startswith("auth.") for i in log)
    assert client.get("/v1/admin/audit?group=ngawur", headers=admin).status_code == 422
    assert client.get("/v1/admin/audit?q=dr_b", headers=admin).json()["total"] >= 1
    assert len(client.get("/v1/admin/audit?limit=1", headers=admin).json()["items"]) == 1


def test_log_audit_dokter_biasa_ditolak_dan_csv_aman_dari_injeksi_rumus(client, tenant, admin):
    assert client.get("/v1/admin/audit", headers=login(client, tenant, "dr_b")).status_code == 403
    assert client.get("/v1/admin/audit.csv", headers=login(client, tenant, "dr_b")).status_code == 403
    with engine().begin() as c:                                                      # nama pelaku berbahaya untuk Excel
        c.execute(text("UPDATE users SET display_name=:n WHERE id=:i"), dict(n='=HYPERLINK("http://x")', i=tenant["doctors"]["dr_a"]))
    new_user(client, admin)
    r = client.get("/v1/admin/audit.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    body = r.content.decode("utf-8")
    assert body.startswith("\ufeffWaktu,Pelaku")                                     # BOM agar Excel membaca UTF-8
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body                       # sel berawalan '=' diberi tanda petik
    with engine().begin() as c:
        assert c.execute(text("SELECT count(*) FROM audit_log WHERE client_id=:c AND action='admin.audit_exported'"), dict(c=tenant["id"])).scalar() >= 1   # ekspor sendiri tercatat


# ---------------------------------------------------------------- riwayat pengiriman SIMRS & kirim ulang
def _failed_submission(ref, status="approved", ago="1 hour"):
    cid, uid = ref["id"], ref["doctors"]["dr_a"]
    with engine().begin() as c:
        sid = c.execute(text("INSERT INTO consult_sessions(client_id, user_id, no_rawat, status, consent_at, consent_by) "
                             "VALUES (:c,:u,:n,CAST(:st AS session_status),now(),'x') RETURNING id"),
                        dict(c=cid, u=uid, n="RK" + uuid.uuid4().hex[:5], st=status)).scalar()
        soap = c.execute(text("INSERT INTO soap_notes(client_id, session_id, version, source, created_by, approved_by, approved_at) "
                              "VALUES (:c,:s,1,'dokter',:u,:u,now()) RETURNING id"), dict(c=cid, s=sid, u=uid)).scalar()
        sub = c.execute(text("INSERT INTO simrs_submissions(client_id, session_id, soap_id, adapter, status, response_code, error_code, submitted_at) "
                             "VALUES (:c,:s,:n,'mock','failed',503,'timeout', now() - CAST(:a AS interval)) RETURNING id"),
                        dict(c=cid, s=sid, n=soap, a=ago)).scalar()
    return str(sid), str(sub)


def test_riwayat_pengiriman_dan_kirim_ulang_berhasil(client, tenant, admin):
    sid, sub = _failed_submission(tenant)
    lain = other_tenant()
    d = client.get("/v1/admin/integration/submissions", headers=admin).json()
    it = next(i for i in d["items"] if i["id"] == sub)
    assert (it["status"], it["error_code"], it["response_code"], it["can_retry"], it["doctor"]) == ("failed", "timeout", 503, True, "dr_a")
    assert client.get("/v1/admin/integration/submissions?status=succeeded", headers=admin).json()["total"] == 0
    assert client.get("/v1/admin/integration/submissions?status=ngawur", headers=admin).status_code == 422
    assert client.post(f"/v1/admin/integration/submissions/{sub}/retry", headers=login(client, tenant, "dr_b")).status_code == 403
    r = client.post(f"/v1/admin/integration/submissions/{sub}/retry", headers=admin)
    assert r.status_code == 200 and r.json()["ok"] is True
    with engine().begin() as c:
        assert c.execute(text("SELECT status FROM consult_sessions WHERE id=:s"), dict(s=sid)).scalar() == "submitted"
        assert c.execute(text("SELECT count(*) FROM audit_log WHERE client_id=:c AND action='simrs.resubmit'"), dict(c=tenant["id"])).scalar() == 1
    after = client.get("/v1/admin/integration/submissions", headers=admin).json()["items"]
    assert not next(i for i in after if i["id"] == sub)["can_retry"]               # sudah berhasil terkirim
    assert client.post(f"/v1/admin/integration/submissions/{sub}/retry", headers=admin).json()["detail"] == "already_submitted"   # tak dikirim dua kali
    assert client.post(f"/v1/admin/integration/submissions/{uuid.uuid4()}/retry", headers=admin).status_code == 404
    assert lain["cid"] not in str(after)


def test_kirim_ulang_gagal_tetap_bisa_diulang_dan_sesi_belum_disetujui_ditolak(client, tenant, admin, monkeypatch):
    from app.adapters.base import SubmitResult
    from app.adapters.mock import MockAdapter
    sid, sub = _failed_submission(tenant)
    monkeypatch.setattr(MockAdapter, "submit_soap", lambda self, **k: SubmitResult(False, 500, "boom"))
    r = client.post(f"/v1/admin/integration/submissions/{sub}/retry", headers=admin).json()
    assert (r["ok"], r["error_code"]) == (False, "boom")
    items = client.get("/v1/admin/integration/submissions", headers=admin).json()["items"]
    assert sum(1 for i in items if i["session_id"] == sid and i["status"] == "failed") == 2 and any(i["can_retry"] for i in items if i["session_id"] == sid)
    _, sub2 = _failed_submission(tenant, status="review")                            # sesi belum/tidak disetujui
    assert client.post(f"/v1/admin/integration/submissions/{sub2}/retry", headers=admin).json()["detail"] == "not_approved"
    lain = other_tenant()
    other_sub = _failed_submission({"id": lain["cid"], "doctors": {"dr_a": lain["uid"]}})[1]
    assert client.post(f"/v1/admin/integration/submissions/{other_sub}/retry", headers=admin).status_code == 404   # milik RS lain


def test_log_webhook_dan_hasil_uji_koneksi_tersimpan(client, tenant, admin):
    assert client.get("/v1/admin/integration", headers=admin).json()["last_test"] is None
    with engine().begin() as c:
        for act, aft in (("webhook.sent", '{"event": "session.processed"}'), ("webhook.failed", '{"event": "session.approved", "error": "ConnectError"}')):
            c.execute(text("INSERT INTO audit_log(client_id, actor_type, action, after) VALUES (:c,'system',:a,CAST(:f AS jsonb))"), dict(c=tenant["id"], a=act, f=aft))
    log = client.get("/v1/admin/integration/webhook-log", headers=admin).json()["items"]
    assert [(i["ok"], i["event"]) for i in log[:2]] == [(False, "session.approved"), (True, "session.processed")] and log[0]["error"] == "ConnectError"
    assert client.post("/v1/admin/integration/test", headers=admin).json()["ok"] is True
    t = client.get("/v1/admin/integration", headers=admin).json()["last_test"]
    assert t["ok"] is True and t["at"] and t["detail"] == "ok"                      # tersimpan, tak perlu menguji ulang untuk melihat status


def test_status_sistem_ditolak_untuk_admin_rs(client, tenant, admin):
    assert client.get("/v1/platform/system", headers=admin).status_code == 403     # admin RS tak perlu melihat urusan server


def test_log_audit_keterangan_manusiawi_ip_tanpa_mask_dan_pelaku_sistem(client, tenant, admin):
    client.put("/v1/admin/settings/privacy", json={"retention_days": 14}, headers=admin)
    with engine().begin() as c:
        c.execute(text("INSERT INTO audit_log(client_id, actor_type, action, after) VALUES (:c,'system','webhook.failed',CAST(:f AS jsonb))"),
                  dict(c=tenant["id"], f='{"event": "session.approved", "error": "ConnectError", "attempt": 2}'))
    items = client.get("/v1/admin/audit?limit=50", headers=admin).json()["items"]
    p = next(i for i in items if i["action"] == "admin.privacy_set")
    assert "masa simpan (hari): 14" in p["detail"] and "teks persetujuan kustom: tidak" in p["detail"]      # bukan retention_days=14 / False
    assert p["actor_type"] == "pengguna"
    with engine().begin() as c:                                                                             # TestClient tak punya IP sungguhan
        c.execute(text("INSERT INTO audit_log(client_id, actor_type, action, ip) VALUES (:c,'dokter','auth.login',CAST('203.0.113.7' AS inet))"), dict(c=tenant["id"]))
    masuk = next(i for i in client.get("/v1/admin/audit?group=login&limit=50", headers=admin).json()["items"] if i["ip"])
    assert masuk["ip"] == "203.0.113.7"                                                                     # bukan 203.0.113.7/32
    assert client.get("/v1/admin/audit?q=203.0.113", headers=admin).json()["total"] == 1                    # IP bisa dicari
    w = next(i for i in items if i["action"] == "webhook.failed")
    assert (w["actor"], w["actor_type"]) == ("Sistem", "otomatis") and "percobaan ke: 2" in w["detail"]
