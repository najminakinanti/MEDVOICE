"""API admin RS untuk halaman Pengguna, Integrasi SIMRS, dan Pengaturan.
Setiap endpoint hanya menyentuh client (rumah sakit) milik admin yang login; semua perubahan dicatat di audit_log
(tanpa kata sandi, kunci, atau rahasia webhook di dalam log)."""
import csv
import io
import json
import re
import secrets
import time
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import security
from .adapters import adapter_names, get_adapter
from .audit import audit
from .config import get_settings
from .db import get_conn
from .deps import Principal, known_origins, require_admin, require_user_manager

router = APIRouter(prefix="/v1/admin")

ROLES = ("dokter", "admin")
MIN_PASSWORD = 10
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
NIP = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,60}$")
UNIQUE_ERR = {
    "users_email_uq": "email_taken", "users_nip_uq": "nip_taken",
    "users_client_id_username_key": "username_taken", "users_client_id_simrs_user_id_key": "simrs_user_id_taken",
}
USER_COLS = "u.id, u.username, u.display_name, u.email, u.nip, u.simrs_user_id, u.role, u.active, u.last_login_at, u.created_at, u.title"


def _log(conn, p: Principal, action: str, entity: str | None = None, entity_id=None, before=None, after=None,
         client_id: str | None = None) -> None:
    """client_id = RS yang terdampak (untuk tindakan superadmin lintas RS); bawaan: RS si pelaku."""
    audit(conn, action=action, actor_type="dokter", actor_id=p.user_id, client_id=client_id or p.client_id,
          entity=entity, entity_id=entity_id and str(entity_id), before=before, after=after, ip=p.ip)


def _norm(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _iso(d) -> str | None:
    return d.isoformat() if d else None


# ---------------------------------------------------------------- pengguna
# Logika pengguna dipakai dua pintu: /admin/users (admin RS atau superadmin, client-nya sendiri) dan
# /platform/hospitals/{id}/users (superadmin, RS mana pun). Karena itu fungsinya menerima client_id sasaran.
def _user(r, me: str) -> dict:
    return {"id": str(r[0]), "username": r[1], "display_name": r[2], "email": r[3], "nip": r[4], "simrs_user_id": r[5],
            "role": r[6], "active": r[7], "last_login_at": _iso(r[8]), "created_at": _iso(r[9]), "title": r[10],
            "is_self": str(r[0]) == me}


def roles_for(conn, client_id: str) -> tuple[str, ...]:
    """Peran yang boleh dipasang pada pengguna client ini, dari tabel `roles` menurut cakupannya
    (client platform -> scope 'platform'; RS -> 'hospital'), urut dari terendah. Elemen terakhir = peran tertinggi
    di client itu (dipakai untuk aturan 'minimal satu yang aktif')."""
    rows = conn.execute(text(
        "SELECT r.code FROM roles r WHERE r.scope = (SELECT CASE WHEN is_platform THEN 'platform' ELSE 'hospital' END "
        "FROM clients WHERE id=:c) ORDER BY r.rank"), dict(c=client_id)).all()
    return tuple(r[0] for r in rows)


def role_catalog(conn) -> list[dict]:
    rows = conn.execute(text("SELECT code, label, scope, rank, description FROM roles ORDER BY rank")).all()
    return [{"code": r[0], "label": r[1], "scope": r[2], "rank": r[3], "description": r[4]} for r in rows]


def _get_user(conn, client_id: str, user_id: str):
    try:
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(404, "user_not_found") from None
    row = conn.execute(text(f"SELECT {USER_COLS} FROM users u WHERE u.id=:i AND u.client_id=:c"),
                       dict(i=user_id, c=client_id)).first()
    if not row:
        raise HTTPException(404, "user_not_found")            # pengguna RS lain pun 404, bukan 403 (tak membocorkan)
    return row


def _check_identity(email: str | None, nip: str | None) -> None:
    if email and not EMAIL.match(email):
        raise HTTPException(422, "email_invalid")
    if nip and not NIP.match(nip):
        raise HTTPException(422, "nip_invalid")
    if not email and not nip:
        raise HTTPException(422, "identity_required")        # login memakai email atau NIP


def _write(conn, sql: str, params: dict):
    """Tulis dalam savepoint: pelanggaran keunikan/aturan jadi 409/422 yang jelas, bukan membatalkan seluruh transaksi."""
    try:
        with conn.begin_nested():
            return conn.execute(text(sql), params)
    except IntegrityError as e:
        if getattr(e.orig, "sqlstate", None) in ("23514", "23503"):     # penjaga peran di database (trigger / kunci asing ke tabel roles)
            raise HTTPException(422, "role_invalid") from None
        name = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
        raise HTTPException(409, UNIQUE_ERR.get(name, "duplicate")) from None


def _password(given: str | None) -> tuple[str, bool]:
    """(kata sandi, dibuat otomatis?). Kosong -> dibuat acak; ditampilkan SEKALI kepada admin."""
    if not given:
        return secrets.token_urlsafe(9), True
    if len(given) < MIN_PASSWORD:
        raise HTTPException(422, "password_too_short")
    return given, False


class UserIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    nip: str | None = None
    username: str | None = None
    simrs_user_id: str | None = Field(default=None, max_length=100)
    role: str | None = None                    # kosong = peran terendah yang sah untuk client ini
    title: str | None = Field(default=None, max_length=80)      # jabatan (teks bebas), mis. "Dokter Umum", "Sp.PD"
    password: str | None = None


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = None
    nip: str | None = None
    simrs_user_id: str | None = Field(default=None, max_length=100)
    role: str | None = None
    title: str | None = Field(default=None, max_length=80)
    active: bool | None = None


class ResetIn(BaseModel):
    password: str | None = None


def list_users_in(conn, client_id: str, me: str, q: str) -> dict:
    rows = conn.execute(text(f"SELECT {USER_COLS} FROM users u WHERE u.client_id=:c "
                             "ORDER BY u.active DESC, lower(u.display_name)"), dict(c=client_id)).all()
    items = [_user(r, me) for r in rows]
    needle = q.strip().lower()
    if needle:
        items = [u for u in items if needle in " ".join(str(u[k] or "") for k in ("display_name", "email", "nip", "username")).lower()]
    return {"total": len(items), "items": items, "roles": list(roles_for(conn, client_id)),
            "role_labels": {r["code"]: r["label"] for r in role_catalog(conn)}}


def create_user_in(conn, p: Principal, client_id: str, body: UserIn) -> dict:
    roles = roles_for(conn, client_id)
    role = body.role or roles[0]
    if role not in roles:
        raise HTTPException(422, "role_invalid")
    email = (_norm(body.email) or "").lower() or None
    nip = _norm(body.nip)
    _check_identity(email, nip)
    username = _norm(body.username) or (email.split("@")[0] if email else nip)
    if not USERNAME.match(username):
        raise HTTPException(422, "username_invalid")
    pw, generated = _password(body.password)
    row = _write(conn,
                 "INSERT INTO users(client_id, simrs_user_id, username, password_hash, display_name, email, nip, role, title) "
                 "VALUES (:c,:s,:u,:p,:n,:e,:i,:r,:t) RETURNING id",
                 dict(c=client_id, s=_norm(body.simrs_user_id) or username, u=username, p=security.hash_password(pw),
                      n=body.display_name.strip(), e=email, i=nip, r=role, t=_norm(body.title))).first()
    _log(conn, p, "admin.user_created", "users", row[0], after={"role": role}, client_id=client_id)
    out = {"id": str(row[0]), "username": username}
    if generated:
        out["temporary_password"] = pw
    return out


def update_user_in(conn, p: Principal, client_id: str, user_id: str, body: UserPatch) -> dict:
    roles = roles_for(conn, client_id)
    cur = _user(_get_user(conn, client_id, user_id), p.user_id)
    sent = body.model_fields_set
    new = dict(cur)
    if "display_name" in sent and body.display_name:
        new["display_name"] = body.display_name.strip()
    if "email" in sent:
        new["email"] = (_norm(body.email) or "").lower() or None      # null = hapus
    if "nip" in sent:
        new["nip"] = _norm(body.nip)
    if "simrs_user_id" in sent and _norm(body.simrs_user_id):
        new["simrs_user_id"] = _norm(body.simrs_user_id)
    if "title" in sent:
        new["title"] = _norm(body.title)
    if "role" in sent and body.role is not None:
        if body.role not in roles:
            raise HTTPException(422, "role_invalid")
        new["role"] = body.role
    if "active" in sent and body.active is not None:
        new["active"] = body.active
    if "email" in sent or "nip" in sent:        # akun lama tanpa email/NIP (login pakai nama pengguna) tetap bisa diubah hal lainnya
        _check_identity(new["email"], new["nip"])
    if cur["is_self"] and (not new["active"] or new["role"] != cur["role"]):
        raise HTTPException(409, "cannot_modify_self")               # tak boleh mengunci/menurunkan/menaikkan diri sendiri
    top = roles[-1]
    if cur["role"] == top and cur["active"] and not (new["role"] == top and new["active"]):
        others = conn.execute(text("SELECT count(*) FROM users WHERE client_id=:c AND role=:r AND active AND id<>:i"),
                              dict(c=client_id, r=top, i=user_id)).scalar()
        if not others:
            raise HTTPException(409, "last_admin")                   # setiap RS/platform wajib punya minimal satu pengelola aktif
    _write(conn, "UPDATE users SET display_name=:n, email=:e, nip=:i, simrs_user_id=:s, role=:r, active=:a, title=:t WHERE id=:id AND client_id=:c",
           dict(n=new["display_name"], e=new["email"], i=new["nip"], s=new["simrs_user_id"], r=new["role"],
                a=new["active"], t=new["title"], id=user_id, c=client_id))
    changed = sorted(k for k in ("display_name", "email", "nip", "simrs_user_id", "role", "active", "title") if new[k] != cur[k])
    _log(conn, p, "admin.user_updated", "users", user_id, client_id=client_id,
         before={k: cur[k] for k in changed if k in ("role", "active")},
         after={"fields": changed, **{k: new[k] for k in changed if k in ("role", "active")}})
    return {"ok": True}


def reset_password_in(conn, p: Principal, client_id: str, user_id: str, body: ResetIn) -> dict:
    _get_user(conn, client_id, user_id)
    if user_id == p.user_id:
        raise HTTPException(409, "use_profile")                      # kata sandi sendiri diganti lewat Profil (wajib sandi lama)
    pw, generated = _password(body.password)
    conn.execute(text("UPDATE users SET password_hash=:h WHERE id=:i AND client_id=:c"),
                 dict(h=security.hash_password(pw), i=user_id, c=client_id))
    _log(conn, p, "admin.password_reset", "users", user_id, client_id=client_id)
    return {"ok": True, **({"temporary_password": pw} if generated else {})}


@router.get("/users")
def list_users(q: str = "", p: Principal = Depends(require_user_manager), conn=Depends(get_conn)):
    return list_users_in(conn, p.client_id, p.user_id, q)


@router.post("/users", status_code=201)
def create_user(body: UserIn, p: Principal = Depends(require_user_manager), conn=Depends(get_conn)):
    return create_user_in(conn, p, p.client_id, body)


@router.put("/users/{user_id}")
def update_user(user_id: str, body: UserPatch, p: Principal = Depends(require_user_manager), conn=Depends(get_conn)):
    return update_user_in(conn, p, p.client_id, user_id, body)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, body: ResetIn, p: Principal = Depends(require_user_manager), conn=Depends(get_conn)):
    return reset_password_in(conn, p, p.client_id, user_id, body)


# ---------------------------------------------------------------- integrasi SIMRS
def _client(conn, p: Principal):
    return conn.execute(text("SELECT webhook_url, allowed_origins, simrs_adapter, rate_limit_per_min, monthly_quota, "
                             "last_test_at, last_test_ok, last_test_ms, last_test_detail FROM clients WHERE id=:c"),
                        dict(c=p.client_id)).first()


@router.get("/integration")
def integration(p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    c = _client(conn, p)
    keys = conn.execute(text("SELECT key_prefix, label, created_at, last_used_at, revoked_at FROM api_keys "
                             "WHERE client_id=:c ORDER BY created_at DESC"), dict(c=p.client_id)).all()
    used = conn.execute(text("SELECT count(*) FROM consult_sessions WHERE client_id=:c AND created_at >= date_trunc('month', now())"),
                        dict(c=p.client_id)).scalar()
    sub = conn.execute(text("SELECT max(submitted_at), max(submitted_at) FILTER (WHERE status='succeeded'), "
                            "count(*) FILTER (WHERE status='failed' AND submitted_at > now() - interval '7 days') "
                            "FROM simrs_submissions WHERE client_id=:c"), dict(c=p.client_id)).first()
    return {"adapter": c[2], "adapters": adapter_names(), "webhook_url": c[0], "allowed_origins": list(c[1] or []),
            "rate_limit_per_min": c[3], "monthly_quota": c[4], "sessions_this_month": used,
            "last_submission_at": _iso(sub[0]), "last_success_at": _iso(sub[1]), "failed_7d": sub[2],
            "last_test": {"at": _iso(c[5]), "ok": c[6], "latency_ms": c[7], "detail": c[8]} if c[5] else None,
            "keys": [{"prefix": k[0], "label": k[1], "created_at": _iso(k[2]), "last_used_at": _iso(k[3]),
                      "revoked_at": _iso(k[4])} for k in keys]}


class WebhookIn(BaseModel):
    url: str | None = None


@router.put("/integration/webhook")
def set_webhook(body: WebhookIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    url = _norm(body.url)
    if url:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or len(url) > 500:
            raise HTTPException(422, "webhook_url_invalid")
    conn.execute(text("UPDATE clients SET webhook_url=:u WHERE id=:c"), dict(u=url, c=p.client_id))
    _log(conn, p, "admin.webhook_set", "clients", p.client_id, after={"configured": bool(url), "scheme": urlparse(url).scheme if url else None})
    return {"ok": True, "webhook_url": url}


@router.get("/integration/webhook-secret")
def webhook_secret(p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    _log(conn, p, "admin.webhook_secret_viewed", "clients", p.client_id)       # melihat rahasia = tindakan sensitif, dicatat
    return {"secret": security.webhook_secret(p.client_id)}


class KeyIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)


@router.post("/integration/keys", status_code=201)
def create_key(body: KeyIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    key, prefix, h = security.new_api_key()
    conn.execute(text("INSERT INTO api_keys(client_id, key_prefix, key_hash, label) VALUES (:c,:p,:h,:l)"),
                 dict(c=p.client_id, p=prefix, h=h, l=body.label.strip()))
    _log(conn, p, "admin.key_created", "api_keys", prefix)
    return {"key": key, "prefix": prefix, "label": body.label.strip()}      # kunci utuh hanya muncul SEKALI ini


@router.post("/integration/keys/{prefix}/revoke")
def revoke_key(prefix: str, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    n = conn.execute(text("UPDATE api_keys SET revoked_at=now() WHERE client_id=:c AND key_prefix=:p AND revoked_at IS NULL"),
                     dict(c=p.client_id, p=prefix)).rowcount
    if not n:
        raise HTTPException(404, "key_not_found")
    _log(conn, p, "admin.key_revoked", "api_keys", prefix)
    return {"ok": True}


class AdapterIn(BaseModel):
    adapter: str


@router.put("/integration/adapter")
def set_adapter(body: AdapterIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    if body.adapter not in adapter_names():
        raise HTTPException(422, "adapter_unknown")
    before = _client(conn, p)[2]
    conn.execute(text("UPDATE clients SET simrs_adapter=:a WHERE id=:c"), dict(a=body.adapter, c=p.client_id))
    _log(conn, p, "admin.adapter_set", "clients", p.client_id, before={"adapter": before}, after={"adapter": body.adapter})
    return {"ok": True}


class OriginsIn(BaseModel):
    origins: list[str] = Field(max_length=10)


@router.put("/integration/origins")
def set_origins(body: OriginsIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    clean = []
    for o in body.origins:
        o = o.strip()
        u = urlparse(o)
        if u.scheme not in ("http", "https") or not u.hostname or f"{u.scheme}://{u.netloc}" != o:
            raise HTTPException(422, "origin_invalid")                # hanya skema://host[:port], tanpa path
        if o not in clean:
            clean.append(o)
    conn.execute(text("UPDATE clients SET allowed_origins=:o WHERE id=:c"), dict(o=clean, c=p.client_id))
    known_origins._cache = None                                         # CORS langsung memakai daftar baru
    _log(conn, p, "admin.origins_set", "clients", p.client_id, after={"count": len(clean)})
    return {"ok": True, "allowed_origins": clean}


def _save_test(conn, p: Principal, ok: bool, ms: int | None, detail: str) -> None:
    conn.execute(text("UPDATE clients SET last_test_at=now(), last_test_ok=:o, last_test_ms=:m, last_test_detail=:d WHERE id=:c"),
                 dict(o=ok, m=ms, d=detail, c=p.client_id))


@router.post("/integration/test")
def test_integration(p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Uji sambungan ke SIMRS lewat adapter yang aktif (membaca antrean; tidak menulis apa pun). Hasilnya disimpan."""
    adapter = get_adapter(_client(conn, p)[2])
    fn = getattr(adapter, "list_queue", None)
    if not fn:
        _save_test(conn, p, True, None, "no_test_available")
        return {"ok": True, "adapter": adapter.name, "latency_ms": None, "detail": "no_test_available"}
    t = time.perf_counter()
    try:
        fn(p.doctor_simrs_id)
    except Exception as e:  # noqa: BLE001 - hanya jenis galat, tanpa pesan (bisa memuat data)
        ms = round((time.perf_counter() - t) * 1000)
        _save_test(conn, p, False, ms, type(e).__name__)
        return {"ok": False, "adapter": adapter.name, "latency_ms": ms, "detail": type(e).__name__}
    ms = round((time.perf_counter() - t) * 1000)
    _save_test(conn, p, True, ms, "ok")
    return {"ok": True, "adapter": adapter.name, "latency_ms": ms, "detail": "ok"}


@router.get("/integration/submissions")
def submissions(status: str = "", limit: int = 20, offset: int = 0, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Riwayat pengiriman SOAP ke SIMRS untuk RS ini (terbaru dulu). `can_retry` = gagal, sesinya masih berstatus disetujui,
    dan belum pernah berhasil terkirim."""
    if status and status not in ("succeeded", "failed", "pending"):
        raise HTTPException(422, "status_invalid")
    limit = min(max(limit, 1), 100)
    where = "sub.client_id=:c" + (" AND sub.status=:st" if status else "")
    params = dict(c=p.client_id, st=status, l=limit, o=max(offset, 0))
    total = conn.execute(text(f"SELECT count(*) FROM simrs_submissions sub WHERE {where}"), params).scalar()
    rows = conn.execute(text(
        "SELECT sub.id, sub.session_id, s.no_rawat, u.display_name, sub.adapter, sub.status, sub.response_code, sub.error_code, "
        "sub.submitted_at, s.status, EXISTS (SELECT 1 FROM simrs_submissions x WHERE x.session_id=sub.session_id AND x.status='succeeded') "
        f"FROM simrs_submissions sub JOIN consult_sessions s ON s.id=sub.session_id LEFT JOIN users u ON u.id=s.user_id WHERE {where} "
        "ORDER BY sub.submitted_at DESC, sub.id LIMIT :l OFFSET :o"), params).all()
    return {"total": total, "items": [
        {"id": str(r[0]), "session_id": str(r[1]), "no_rawat": r[2], "doctor": r[3], "adapter": r[4], "status": r[5],
         "response_code": r[6], "error_code": r[7], "submitted_at": _iso(r[8]),
         "can_retry": r[5] == "failed" and r[9] == "approved" and not r[10]} for r in rows]}


@router.post("/integration/submissions/{sub_id}/retry")
def retry_submission(sub_id: str, bg: BackgroundTasks, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Kirim ulang SOAP yang gagal terkirim. Memakai logika kirim yang sama dengan tombol kirim dokter (idempotensi sama)."""
    from .routes import _later, do_submit
    try:
        uuid.UUID(sub_id)
    except ValueError:
        raise HTTPException(404, "submission_not_found") from None
    r = conn.execute(text(
        "SELECT s.id, s.client_id, s.user_id, s.no_rawat, s.status, sub.status FROM simrs_submissions sub "
        "JOIN consult_sessions s ON s.id=sub.session_id WHERE sub.id=:i AND sub.client_id=:c"), dict(i=sub_id, c=p.client_id)).first()
    if not r:
        raise HTTPException(404, "submission_not_found")                 # milik RS lain pun 404
    sess = {"id": r[0], "client_id": r[1], "user_id": r[2], "no_rawat": r[3], "status": r[4]}
    if conn.execute(text("SELECT 1 FROM simrs_submissions WHERE session_id=:s AND status='succeeded'"), dict(s=r[0])).first():
        raise HTTPException(409, "already_submitted")
    if r[4] != "approved":
        raise HTTPException(409, "not_approved")
    res, new_id = do_submit(conn, client_id=p.client_id, adapter_name=p.simrs_adapter, s=sess, actor_type="dokter",
                            actor_id=p.user_id, ip=p.ip, action="simrs.resubmit")
    if res.ok:
        _later(bg, str(r[0]), "session.submitted")
    return {"ok": res.ok, "error_code": res.error_code, "submission_id": str(new_id)}


@router.get("/integration/webhook-log")
def webhook_log(limit: int = 30, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Pengiriman webhook terbaru (berhasil/gagal) dari log audit. Isinya hanya id sesi + nama event."""
    rows = conn.execute(text(
        "SELECT a.ts, a.action, a.session_id, a.after FROM audit_log a WHERE a.client_id=:c AND a.action LIKE 'webhook.%' "
        "ORDER BY a.id DESC LIMIT :l"), dict(c=p.client_id, l=min(max(limit, 1), 100))).all()
    return {"items": [{"at": _iso(r[0]), "ok": r[1] == "webhook.sent", "session_id": str(r[2]) if r[2] else None,
                       "event": (r[3] or {}).get("event"), "attempt": (r[3] or {}).get("attempt"),
                       "error": (r[3] or {}).get("error") or (r[3] or {}).get("error_code")} for r in rows]}


# ---------------------------------------------------------------- pengaturan
def _probe_stt() -> dict:
    try:
        d = httpx.get(get_settings().stt_url.rstrip("/") + "/health", timeout=3).json()
        return {"reachable": True, "device": d.get("device"), "model": d.get("model"),
                "stream_final_model": d.get("stream_final_model"), "loaded": d.get("loaded", [])}
    except Exception:  # noqa: BLE001
        return {"reachable": False}


def _probe_llm() -> dict:
    s = get_settings()
    out = {"backend": s.llm_backend, "model": s.llm_model, "reachable": False, "installed": None}
    if s.llm_backend != "ollama":
        return out
    try:
        names = [m["name"] for m in httpx.get(s.llm_base_url.rstrip("/") + "/api/tags", timeout=3).json().get("models", [])]
        out.update(reachable=True, installed=s.llm_model in names)
    except Exception:  # noqa: BLE001
        pass
    return out


@router.get("/settings")
def settings(p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Pengaturan tingkat rumah sakit. Hal teknis server (STT/LLM, GPU, terminologi) sengaja tidak di sini: lihat /platform/system."""
    s = get_settings()
    c = conn.execute(text("SELECT rate_limit_per_min, monthly_quota, retention_days, session_minutes, consent_text FROM clients WHERE id=:c"),
                     dict(c=p.client_id)).first()
    tr = conn.execute(text("SELECT count(*) FILTER (WHERE purged_at IS NULL), "
                           "count(*) FILTER (WHERE purged_at IS NULL AND purge_after < now()) FROM transcripts WHERE client_id=:c"),
                      dict(c=p.client_id)).first()
    retention = c[2] or s.transcript_retention_days
    return {
        "retention_days": retention, "keep_audio": s.keep_audio,
        "privacy": {"retention_days": retention, "retention_custom": c[2], "retention_default": s.transcript_retention_days,
                    "consent_text": c[4], "keep_audio": s.keep_audio},
        "security": {"session_minutes": c[3] or s.jwt_ttl_minutes, "session_custom": c[3], "session_default": s.jwt_ttl_minutes},
        "limits": {"rate_limit_per_min": c[0], "monthly_quota": c[1]},
        "transcripts": {"stored": tr[0], "due_for_purge": tr[1]},
        "roles": role_catalog(conn),
    }


class PrivacyIn(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=365)         # null = bawaan server
    consent_text: str | None = Field(default=None, max_length=2000)         # null/kosong = teks bawaan aplikasi


@router.put("/settings/privacy")
def set_privacy(body: PrivacyIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    sent = body.model_fields_set
    cur = conn.execute(text("SELECT retention_days, consent_text FROM clients WHERE id=:c"), dict(c=p.client_id)).first()
    days, consent = cur[0], cur[1]
    if "retention_days" in sent:
        days = body.retention_days
    if "consent_text" in sent:
        consent = _norm(body.consent_text)
    conn.execute(text("UPDATE clients SET retention_days=:d, consent_text=:t WHERE id=:c"), dict(d=days, t=consent, c=p.client_id))
    applied = None
    if "retention_days" in sent:
        eff = days or get_settings().transcript_retention_days
        # berlaku juga untuk transkrip yang sudah tersimpan (memperpendek masa simpan tidak boleh menunggu data baru)
        applied = conn.execute(text("UPDATE transcripts SET purge_after = created_at + make_interval(days => :d) "
                                    "WHERE client_id=:c AND purged_at IS NULL"), dict(d=eff, c=p.client_id)).rowcount
    _log(conn, p, "admin.privacy_set", "clients", p.client_id,
         before={"retention_days": cur[0], "consent_custom": bool(cur[1])},
         after={"retention_days": days, "consent_custom": bool(consent), "transcripts_recalculated": applied})
    return {"ok": True, "transcripts_recalculated": applied}


class SecurityIn(BaseModel):
    session_minutes: int | None = Field(default=None, ge=15, le=1440)       # null = bawaan server; berlaku pada login berikutnya


@router.put("/settings/security")
def set_security(body: SecurityIn, p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    before = conn.execute(text("SELECT session_minutes FROM clients WHERE id=:c"), dict(c=p.client_id)).scalar()
    conn.execute(text("UPDATE clients SET session_minutes=:m WHERE id=:c"), dict(m=body.session_minutes, c=p.client_id))
    _log(conn, p, "admin.security_set", "clients", p.client_id, before={"session_minutes": before}, after={"session_minutes": body.session_minutes})
    return {"ok": True}


@router.post("/settings/purge")
def purge(p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Hapus transkrip RS ini yang lewat masa retensi (kebijakan yang sama dengan job terjadwal)."""
    from .soap_pipeline import purge_expired
    r = purge_expired(client_id=p.client_id)
    _log(conn, p, "admin.purge_run", after={"transcripts_purged": r["transcripts_purged"]})
    return {"transcripts_purged": r["transcripts_purged"]}


# ---------------------------------------------------------------- log audit
AUDIT_GROUPS = {
    "login": ("auth.%",),
    "klinis": ("session.%", "soap.%", "review.%", "audio.%", "code.%", "transcript.%"),
    "simrs": ("simrs.%", "webhook.%"),
    "admin": ("admin.%", "platform.%", "user.%"),
}
ACTION_LABEL = {
    "auth.login": "Masuk", "auth.login_failed": "Gagal masuk (kata sandi/akun salah)", "user.password_changed": "Ganti kata sandi sendiri",
    "session.create": "Mulai sesi konsultasi", "session.finish": "Selesai merekam", "audio.upload": "Unggah audio",
    "audio.deleted": "Audio dihapus", "audio.kept_dev": "Audio ditahan (mode uji)", "soap.ai_generated": "Draf SOAP dibuat AI",
    "soap.edit": "SOAP diedit dokter", "soap.approve": "SOAP disetujui dokter", "review.view": "Membuka review SOAP",
    "code.set": "Kode diubah dokter", "transcript.purged": "Transkrip dihapus (retensi)", "simrs.submit": "Kirim SOAP ke SIMRS",
    "simrs.resubmit": "Kirim ulang SOAP ke SIMRS", "webhook.sent": "Webhook terkirim", "webhook.failed": "Webhook gagal",
    "admin.user_created": "Pengguna dibuat", "admin.user_updated": "Pengguna diubah", "admin.password_reset": "Kata sandi pengguna diatur ulang",
    "admin.key_created": "Kunci API dibuat", "admin.key_revoked": "Kunci API dicabut", "admin.webhook_set": "Webhook diubah",
    "admin.webhook_secret_viewed": "Rahasia webhook dilihat", "admin.adapter_set": "Adapter SIMRS diganti", "admin.origins_set": "Origin diubah",
    "admin.privacy_set": "Pengaturan data & privasi diubah", "admin.security_set": "Pengaturan keamanan diubah", "admin.purge_run": "Pembersihan transkrip dijalankan",
    "platform.hospital_created": "Rumah sakit dibuat", "platform.hospital_updated": "Rumah sakit diubah",
}


def _audit_query(conn, p: Principal, group: str, q: str, limit: int, offset: int):
    where, params = ["a.client_id=:c"], {"c": p.client_id}
    if group:
        if group not in AUDIT_GROUPS:
            raise HTTPException(422, "group_invalid")
        where.append("(" + " OR ".join(f"a.action LIKE :g{i}" for i in range(len(AUDIT_GROUPS[group]))) + ")")
        params.update({f"g{i}": pat for i, pat in enumerate(AUDIT_GROUPS[group])})
    if q.strip():
        where.append("(a.action ILIKE :q OR coalesce(u.display_name,'') ILIKE :q OR coalesce(a.actor_id,'') ILIKE :q OR coalesce(host(a.ip),'') ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    w = " AND ".join(where)
    join = "LEFT JOIN users u ON u.id::text = a.actor_id AND u.client_id = a.client_id"
    total = conn.execute(text(f"SELECT count(*) FROM audit_log a {join} WHERE {w}"), params).scalar()
    rows = conn.execute(text(
        f"SELECT a.id, a.ts, a.actor_type, a.actor_id, u.display_name, a.action, a.entity, host(a.ip), a.after, a.session_id "
        f"FROM audit_log a {join} WHERE {w} ORDER BY a.id DESC LIMIT :l OFFSET :o"), {**params, "l": limit, "o": offset}).all()
    return total, rows


DETAIL_KEY = {
    "retention_days": "masa simpan (hari)", "consent_custom": "teks persetujuan kustom", "transcripts_recalculated": "transkrip dihitung ulang",
    "session_minutes": "masa sesi (menit)", "ok": "berhasil", "error_code": "kode galat", "error": "galat", "event": "event", "attempt": "percobaan ke",
    "role": "peran", "active": "aktif", "rows": "jumlah baris", "transcripts_purged": "transkrip dihapus", "name": "nama", "adapter": "adapter",
    "count": "jumlah", "configured": "terisi", "scheme": "skema", "prefix": "awalan",
}
DETAIL_FIELD = {"display_name": "nama", "email": "email", "nip": "NIP", "simrs_user_id": "ID SIMRS", "role": "peran", "active": "status aktif", "title": "jabatan"}
ACTOR_KIND = {"dokter": "pengguna", "api_client": "kunci API", "system": "otomatis", "ai": "AI"}


def _fmt(v) -> str:
    return "ya" if v is True else "tidak" if v is False else str(v)


def _audit_item(r) -> dict:
    after = r[8] if isinstance(r[8], dict) else {}
    parts = []
    if after.get("fields"):
        parts.append("diubah: " + ", ".join(DETAIL_FIELD.get(f, f) for f in after["fields"]))
    parts += [f"{DETAIL_KEY.get(k, k)}: {_fmt(v)}" for k, v in after.items() if v is not None and k != "fields"]
    actor = "Sistem" if r[2] == "system" else (r[4] or r[3] or r[2])
    return {"id": r[0], "at": _iso(r[1]), "actor_type": ACTOR_KIND.get(r[2], r[2]), "actor": actor, "action": r[5],
            "label": ACTION_LABEL.get(r[5], r[5]), "entity": r[6], "ip": r[7], "detail": "; ".join(parts)[:200],
            "session_id": str(r[9]) if r[9] else None}


@router.get("/audit")
def audit_list(group: str = "", q: str = "", limit: int = 50, offset: int = 0,
               p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    """Log audit RS ini (terbaru dulu). Hanya metadata: tidak pernah memuat isi transkrip, kata sandi, atau kunci."""
    total, rows = _audit_query(conn, p, group, q, min(max(limit, 1), 200), max(offset, 0))
    return {"total": total, "items": [_audit_item(r) for r in rows]}


def _csv_safe(v) -> str:
    """Cegah injeksi rumus saat CSV dibuka di Excel: sel yang diawali = + - @ diberi tanda petik."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/audit.csv")
def audit_csv(group: str = "", q: str = "", p: Principal = Depends(require_admin), conn=Depends(get_conn)):
    _, rows = _audit_query(conn, p, group, q, 5000, 0)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Waktu", "Pelaku", "Jenis pelaku", "Aksi", "Kode aksi", "Keterangan", "Objek", "IP"])
    for r in rows:
        it = _audit_item(r)
        w.writerow([_csv_safe(x) for x in (it["at"], it["actor"], it["actor_type"], it["label"], it["action"], it["detail"], it["entity"], it["ip"])])
    _log(conn, p, "admin.audit_exported", after={"rows": len(rows)})
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="log-audit.csv"'})
