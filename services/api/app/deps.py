import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text

from . import ratelimit, security
from .db import engine, get_conn


@dataclass
class Principal:
    kind: str                    # "api_key" | "doctor"
    client_id: str
    user_id: str | None
    client_name: str
    simrs_adapter: str
    allowed_origins: list[str]
    monthly_quota: int | None
    doctor_simrs_id: str | None = None
    ip: str | None = None
    session_scope: str | None = None     # token widget: hanya untuk satu sesi
    role: str | None = None              # "dokter" | "admin" (hanya untuk login pengguna)


def _origin_ok(origin: str | None, host: str | None, origins: list[str]) -> bool:
    if not origin:
        return True
    if urlparse(origin).netloc == host:
        return True       # same-origin (UI yang dilayani engine sendiri)
    return origin in origins


def get_principal(request: Request, conn=Depends(get_conn)) -> Principal:
    return principal_from(conn, key=request.headers.get("x-api-key"), auth=request.headers.get("authorization", ""),
                          origin=request.headers.get("origin"), host=request.headers.get("host"),
                          ip=request.client.host if request.client else None)


def principal_from(conn, *, key: str | None, auth: str, origin: str | None, host: str | None, ip: str | None) -> Principal:
    """Autentikasi dari kredensial mentah (dipakai request HTTP dan WebSocket)."""
    row = None
    kind = None
    user_id = doctor_simrs = role = None
    scope = None
    if key:
        row = conn.execute(text(
            "SELECT c.id, c.name, c.simrs_adapter, c.allowed_origins, c.monthly_quota, c.rate_limit_per_min, k.id "
            "FROM api_keys k JOIN clients c ON c.id=k.client_id "
            "WHERE k.key_hash=:h AND k.revoked_at IS NULL AND c.active"),
            dict(h=security.hash_api_key(key))).first()
        kind = "api_key"
        if row:
            conn.execute(text("UPDATE api_keys SET last_used_at=now() WHERE id=:i"), dict(i=row[6]))
    elif auth.lower().startswith("bearer "):
        claims = security.decode_token(auth[7:].strip())
        if claims:
            row = conn.execute(text(
                "SELECT c.id, c.name, c.simrs_adapter, c.allowed_origins, c.monthly_quota, c.rate_limit_per_min, d.id, d.simrs_user_id, d.role "
                "FROM users d JOIN clients c ON c.id=d.client_id "
                "WHERE d.id=:d AND c.id=:c AND d.active AND c.active"),
                dict(d=claims["sub"], c=claims["cid"])).first()
            kind = "doctor"
            if row:
                user_id, doctor_simrs, role = str(row[6]), row[7], row[8]
                scope = claims.get("sid")
    if not row:
        raise HTTPException(401, "unauthorized")
    p = Principal(kind, str(row[0]), user_id, row[1], row[2], list(row[3] or []), row[4],
                  doctor_simrs, ip, scope, role)
    if not _origin_ok(origin, host, p.allowed_origins):
        raise HTTPException(403, "origin_not_allowed")
    if not ratelimit.allow(p.client_id, row[5]):
        raise HTTPException(429, "rate_limited", headers={"Retry-After": str(60 - int(time.time()) % 60)})
    return p


def require_doctor(p: Principal = Depends(get_principal)) -> Principal:
    if p.kind != "doctor":
        raise HTTPException(403, "doctor_login_required")
    return p


def require_admin(p: Principal = Depends(require_doctor)) -> Principal:
    """Halaman admin (Integrasi SIMRS, Pengaturan) milik client si pelaku: admin RS, atau superadmin di client platform-nya.
    Bukan API key, bukan token widget."""
    if p.session_scope or p.role not in ("admin", "superadmin"):
        raise HTTPException(403, "admin_required")
    return p


def require_user_manager(p: Principal = Depends(require_doctor)) -> Principal:
    """Boleh mengelola pengguna di client-nya sendiri: admin RS (pengguna RS-nya) atau superadmin (akun platform)."""
    if p.session_scope or p.role not in ("admin", "superadmin"):
        raise HTTPException(403, "admin_required")
    return p


def require_superadmin(p: Principal = Depends(require_doctor)) -> Principal:
    """Pengelola platform: kelola semua rumah sakit dan penggunanya (lintas RS). Data klinis RS lain tetap tak terjangkau:
    sesi hanya terlihat oleh pemiliknya di client-nya sendiri (lihat load_session)."""
    if p.session_scope or p.role != "superadmin":
        raise HTTPException(403, "superadmin_required")
    return p


def load_session(conn, p: Principal, session_id: str) -> dict:
    """Muat sesi milik client ini; dokter hanya melihat sesi miliknya. 404 bila tak berhak (tak membocorkan)."""
    sql = ("SELECT id, client_id, user_id, no_rawat, status FROM consult_sessions "
           "WHERE id=:i AND client_id=:c")
    params = dict(i=session_id, c=p.client_id)
    if p.kind == "doctor":
        sql += " AND user_id=:d"
        params["d"] = p.user_id
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(404, "session_not_found") from None
    if p.session_scope and p.session_scope != str(session_id):
        raise HTTPException(404, "session_not_found")          # token widget tidak bisa menyentuh sesi lain
    row = conn.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(404, "session_not_found")
    return dict(row)


def known_origins() -> set[str]:
    """Gabungan origin semua client aktif (untuk header CORS & preflight). Cache 60 detik."""
    now = time.time()
    if known_origins._cache and now - known_origins._cache[0] < 60:
        return known_origins._cache[1]
    with engine().connect() as c:
        rows = c.execute(text("SELECT allowed_origins FROM clients WHERE active")).all()
    s = {o for r in rows for o in (r[0] or [])}
    known_origins._cache = (now, s)
    return s


known_origins._cache = None
