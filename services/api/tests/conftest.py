"""Fixture tes. Integrasi butuh Postgres: set TEST_ADMIN_URL=postgresql://user:pass@host:port/postgres
(database medvoice_test dibuat ulang tiap sesi tes). Tes unit (validator) tidak butuh DB."""
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("TEST_ADMIN_URL")

if ADMIN_URL:
    base = ADMIN_URL.rsplit("/", 1)[0]
    os.environ["DATABASE_URL"] = base.replace("postgresql://", "postgresql+psycopg://") + "/medvoice_test"
else:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost:1/none")
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef"
os.environ["API_KEY_PEPPER"] = "test-pepper-0123456789abcdef"
os.environ["CELERY_EAGER"] = "1"
os.environ["REDIS_URL"] = ""
os.environ["LOGIN_RATE_PER_MIN"] = "1000"
os.environ["AUDIO_DIR"] = tempfile.mkdtemp(prefix="mv_audio_")
os.environ["VOCAB_DIR"] = str(API_DIR / "config")
os.environ["LLM_MODEL"] = "fake-model"


@pytest.fixture(scope="session")
def db():
    if not ADMIN_URL:
        pytest.skip("TEST_ADMIN_URL tidak di-set")
    import psycopg
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS medvoice_test WITH (FORCE)")
        c.execute("CREATE DATABASE medvoice_test")
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR,
                       env=os.environ.copy(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return True


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


@pytest.fixture()
def tenant(db):
    """Client + API key + dua dokter (password: 'passwordku-123')."""
    from sqlalchemy import text

    from app import security
    from app.db import engine
    name = "rs-" + uuid.uuid4().hex[:8]
    key, prefix, h = security.new_api_key()
    with engine().begin() as c:
        cid = c.execute(text("INSERT INTO clients(name, allowed_origins) VALUES (:n, ARRAY['https://web.rs-a.test']) RETURNING id"),
                        dict(n=name)).scalar()
        c.execute(text("INSERT INTO api_keys(client_id, key_prefix, key_hash) VALUES (:c,:p,:h)"), dict(c=cid, p=prefix, h=h))
        docs = {}
        for u in ("dr_a", "dr_b"):
            docs[u] = c.execute(text(
                "INSERT INTO doctors(client_id, simrs_user_id, username, password_hash, display_name) "
                "VALUES (:c,:u,:u,:p,:u) RETURNING id"),
                dict(c=cid, u=u, p=security.hash_password("passwordku-123"))).scalar()
    return {"name": name, "id": str(cid), "key": key, "doctors": docs}


def login(client, tenant, user="dr_a"):
    r = client.post("/v1/auth/login", json={"client": tenant["name"], "username": user, "password": "passwordku-123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}
