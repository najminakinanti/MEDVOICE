"""API superadmin (pengelola platform): kelola rumah sakit dan penggunanya.
Superadmin SENGAJA tidak punya akses ke data klinis (transkrip, SOAP, antrean): yang dikelola di sini hanya akun,
batas pemakaian, dan status RS. Setiap tindakan dicatat di audit_log pada RS yang terdampak."""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import admin_api
from .admin_api import (ResetIn, UserIn, UserPatch, _iso, _log, create_user_in, list_users_in, reset_password_in,
                        update_user_in)
from .config import get_settings
from .db import get_conn
from .deps import Principal, require_superadmin

router = APIRouter(prefix="/v1/platform")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,59}$")

HOSPITAL_SQL = (
    "SELECT c.id, c.name, c.active, c.simrs_adapter, c.rate_limit_per_min, c.monthly_quota, c.created_at, "
    "(SELECT count(*) FROM users u WHERE u.client_id=c.id AND u.active), "
    "(SELECT count(*) FROM users u WHERE u.client_id=c.id AND u.active AND u.role='admin'), "
    "(SELECT count(*) FROM consult_sessions s WHERE s.client_id=c.id AND s.created_at >= date_trunc('month', now())) "
    "FROM clients c WHERE NOT c.is_platform")


def _hospital_dict(r) -> dict:
    return {"id": str(r[0]), "name": r[1], "active": r[2], "adapter": r[3], "rate_limit_per_min": r[4],
            "monthly_quota": r[5], "created_at": _iso(r[6]), "active_users": r[7], "active_admins": r[8],
            "sessions_this_month": r[9]}


def _hospital(conn, hid: str) -> dict:
    """RS sasaran. Client platform bukan 'rumah sakit' dan tidak bisa dipilih di sini."""
    try:
        uuid.UUID(hid)
    except ValueError:
        raise HTTPException(404, "hospital_not_found") from None
    row = conn.execute(text(HOSPITAL_SQL + " AND c.id=:i"), dict(i=hid)).first()
    if not row:
        raise HTTPException(404, "hospital_not_found")
    return _hospital_dict(row)


@router.get("/hospitals")
def list_hospitals(p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    rows = conn.execute(text(HOSPITAL_SQL + " ORDER BY lower(c.name)")).all()
    return {"items": [_hospital_dict(r) for r in rows]}


class AdminIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    nip: str | None = None
    password: str | None = None


class HospitalIn(BaseModel):
    name: str
    rate_limit_per_min: int = Field(default=60, ge=1, le=10000)
    monthly_quota: int | None = Field(default=None, ge=1)
    admin: AdminIn                                   # setiap RS lahir dengan satu admin, supaya tak ada RS tanpa pengelola


@router.post("/hospitals", status_code=201)
def create_hospital(body: HospitalIn, p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    name = body.name.strip().lower()
    if not NAME.match(name):
        raise HTTPException(422, "hospital_name_invalid")           # huruf kecil/angka/strip, 3-60 karakter
    try:
        with conn.begin_nested():                                  # RS dan admin pertamanya: berhasil bersama atau batal bersama
            try:
                cid = conn.execute(text("INSERT INTO clients(name, rate_limit_per_min, monthly_quota) VALUES (:n,:r,:q) RETURNING id"),
                                   dict(n=name, r=body.rate_limit_per_min, q=body.monthly_quota)).scalar()
            except IntegrityError:
                raise HTTPException(409, "hospital_name_taken") from None
            admin = create_user_in(conn, p, str(cid), UserIn(display_name=body.admin.display_name, email=body.admin.email,
                                                             nip=body.admin.nip, password=body.admin.password, role="admin"))
    except HTTPException:
        raise
    _log(conn, p, "platform.hospital_created", "clients", cid, after={"name": name}, client_id=str(cid))
    return {"id": str(cid), "name": name, "admin": admin}


class HospitalPatch(BaseModel):
    active: bool | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=10000)
    monthly_quota: int | None = Field(default=None, ge=1)             # null = tanpa kuota


@router.put("/hospitals/{hid}")
def update_hospital(hid: str, body: HospitalPatch, p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    cur = _hospital(conn, hid)
    sent = body.model_fields_set
    new = {"active": cur["active"], "rate_limit_per_min": cur["rate_limit_per_min"], "monthly_quota": cur["monthly_quota"]}
    if "active" in sent and body.active is not None:
        new["active"] = body.active
    if "rate_limit_per_min" in sent and body.rate_limit_per_min is not None:
        new["rate_limit_per_min"] = body.rate_limit_per_min
    if "monthly_quota" in sent:
        new["monthly_quota"] = body.monthly_quota
    conn.execute(text("UPDATE clients SET active=:a, rate_limit_per_min=:r, monthly_quota=:q WHERE id=:i"),
                 dict(a=new["active"], r=new["rate_limit_per_min"], q=new["monthly_quota"], i=hid))
    changed = sorted(k for k in new if new[k] != cur[k])
    _log(conn, p, "platform.hospital_updated", "clients", hid, client_id=hid,
         before={k: cur[k] for k in changed}, after={k: new[k] for k in changed})
    return {"ok": True}


# Pengguna RS mana pun: logika dan aturan keamanannya sama persis dengan halaman admin RS (admin_api).
@router.get("/hospitals/{hid}/users")
def hospital_users(hid: str, q: str = "", p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    h = _hospital(conn, hid)
    return {**list_users_in(conn, hid, p.user_id, q), "hospital": h}


@router.post("/hospitals/{hid}/users", status_code=201)
def hospital_create_user(hid: str, body: UserIn, p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    _hospital(conn, hid)
    return create_user_in(conn, p, hid, body)


@router.put("/hospitals/{hid}/users/{user_id}")
def hospital_update_user(hid: str, user_id: str, body: UserPatch, p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    _hospital(conn, hid)
    return update_user_in(conn, p, hid, user_id, body)


@router.post("/hospitals/{hid}/users/{user_id}/reset-password")
def hospital_reset_password(hid: str, user_id: str, body: ResetIn, p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    _hospital(conn, hid)
    return reset_password_in(conn, p, hid, user_id, body)


@router.get("/system")
def system(p: Principal = Depends(require_superadmin), conn=Depends(get_conn)):
    """Status teknis server (bukan urusan admin RS): STT, LLM, GPU, tabel terminologi, batas sistem, nilai bawaan."""
    s = get_settings()
    terms = conn.execute(text("SELECT s.code, s.version, count(c.id) FROM terminology_systems s "
                              "LEFT JOIN terminology_codes c ON c.system_id=s.id GROUP BY s.id ORDER BY s.code, s.loaded_at DESC")).all()
    return {
        "stt": admin_api._probe_stt(), "llm": admin_api._probe_llm(),             # lewat modul agar mudah diganti di tes
        "gpu_timeshare": s.gpu_timeshare, "embedding_model": s.embedding_model, "keep_audio": s.keep_audio,
        "max_audio_mb": s.max_audio_mb, "login_rate_per_min": s.login_rate_per_min,
        "default_retention_days": s.transcript_retention_days, "default_session_minutes": s.jwt_ttl_minutes,
        "terminology": [{"code": t[0], "version": t[1], "count": t[2]} for t in terms],
    }
