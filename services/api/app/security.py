import base64
import hashlib
import hmac
import os
import secrets
import time

import jwt

from .config import get_settings


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${_b64(salt)}${_b64(h)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h, expected)
    except Exception:
        return False


def hash_api_key(key: str) -> str:
    pepper = get_settings().api_key_pepper.encode()
    return hmac.new(pepper, key.encode(), hashlib.sha256).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """Return (kunci_asli, prefix, hash). Kunci asli hanya ditampilkan sekali."""
    key = "mvk_" + secrets.token_urlsafe(32)
    return key, key[:8], hash_api_key(key)


def make_token(doctor_id: str, client_id: str, session_id: str | None = None, ttl_s: int | None = None) -> str:
    """JWT dokter. Dengan session_id: token widget yang hanya berlaku untuk SATU sesi."""
    s = get_settings()
    now = int(time.time())
    claims = {"sub": doctor_id, "cid": client_id, "iat": now, "exp": now + (ttl_s or s.jwt_ttl_minutes * 60)}
    if session_id:
        claims["sid"] = session_id
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def webhook_secret(client_id: str) -> str:
    """Rahasia penanda-tangan webhook per client: diturunkan dari pepper (tidak disimpan di DB)."""
    return hmac.new(get_settings().api_key_pepper.encode(), ("webhook:" + client_id).encode(), hashlib.sha256).hexdigest()


def sign_webhook(client_id: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(webhook_secret(client_id).encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return "sha256=" + mac
