"""Login tanpa memilih rumah sakit: dokter dikenali lewat email/NIP, RS diambil dari akun."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import security
from app.db import engine

PW = "passwordku-123"


def _doctor(client_id, username, *, email=None, nip=None):
    with engine().begin() as c:
        return c.execute(text(
            "INSERT INTO users(client_id, simrs_user_id, username, password_hash, display_name, email, nip) "
            "VALUES (:c,:u,:u,:p,:u,:e,:i) RETURNING id"),
            dict(c=client_id, u=username, p=security.hash_password(PW), e=email, i=nip)).scalar()


def _post(http, ident, pw=PW, rs=None):
    body = {"username": ident, "password": pw}
    if rs:
        body["client"] = rs
    return http.post("/v1/auth/login", json=body)


def test_login_email_dan_nip_tanpa_rumah_sakit(client, tenant):
    tag = uuid.uuid4().hex[:8]
    _doctor(tenant["id"], "dr_" + tag, email=f"Anisa.{tag}@RSMedika.test", nip="19" + str(int(tag, 16))[:16])
    nip = "19" + str(int(tag, 16))[:16]
    for ident in (f"anisa.{tag}@rsmedika.test", f"ANISA.{tag}@rsmedika.test ", nip):   # huruf besar/kecil & spasi tak masalah
        r = _post(client, ident)
        assert r.status_code == 200, (ident, r.text)
        me = client.get("/v1/me", headers={"Authorization": "Bearer " + r.json()["access_token"]}).json()
        assert me["client"] == tenant["name"]                      # RS otomatis dari akun dokter


def test_login_salah_ditolak(client, tenant):
    tag = uuid.uuid4().hex[:8]
    _doctor(tenant["id"], "dr_" + tag, email=f"x.{tag}@rs.test")
    assert _post(client, f"x.{tag}@rs.test", "salah-salah-1").status_code == 401
    assert _post(client, f"tidak.ada.{tag}@rs.test").status_code == 401


def test_identitas_ganda_di_dua_rs_ditolak_tanpa_rs_tapi_diterima_dengan_rs(client, tenant):
    tag = uuid.uuid4().hex[:8]
    with engine().begin() as c:
        other = c.execute(text("INSERT INTO clients(name) VALUES (:n) RETURNING id"), dict(n="rs-lain-" + tag)).scalar()
    uname = "dr_sama_" + tag                                       # nama pengguna lama boleh sama di dua RS
    _doctor(tenant["id"], uname)
    _doctor(other, uname)
    assert _post(client, uname).status_code == 401                 # ambigu: sistem tidak menebak RS
    assert _post(client, uname, rs=tenant["name"]).status_code == 200
    assert _post(client, uname, rs="rs-lain-" + tag).status_code == 200


def test_email_dan_nip_unik_di_seluruh_sistem(tenant):
    tag = uuid.uuid4().hex[:8]
    with engine().begin() as c:
        other = c.execute(text("INSERT INTO clients(name) VALUES (:n) RETURNING id"), dict(n="rs-dua-" + tag)).scalar()
    _doctor(tenant["id"], "a_" + tag, email=f"dup.{tag}@rs.test", nip="N" + tag)
    with pytest.raises(IntegrityError):
        _doctor(other, "b_" + tag, email=f"DUP.{tag}@rs.test")      # email sama (tak peduli huruf besar)
    with pytest.raises(IntegrityError):
        _doctor(other, "c_" + tag, nip="N" + tag)


def test_dokter_nonaktif_tidak_bisa_login(client, tenant):
    tag = uuid.uuid4().hex[:8]
    did = _doctor(tenant["id"], "dr_" + tag, email=f"off.{tag}@rs.test")
    with engine().begin() as c:
        c.execute(text("UPDATE users SET active=false WHERE id=:i"), dict(i=did))
    assert _post(client, f"off.{tag}@rs.test").status_code == 401
