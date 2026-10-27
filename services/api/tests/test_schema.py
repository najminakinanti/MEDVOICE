"""Tes skema DB. Butuh Postgres yang sudah dimigrasi: set TEST_DATABASE_URL (postgresql://...)."""
import os

import psycopg
import pytest

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL tidak di-set")


@pytest.fixture()
def conn():
    c = psycopg.connect(URL)
    yield c
    c.rollback()  # semua tes dibatalkan, DB tetap bersih
    c.close()


def _seed(c):
    cl = c.execute("INSERT INTO clients(name) VALUES ('rs-uji') RETURNING id").fetchone()[0]
    dr = c.execute(
        "INSERT INTO users(client_id, simrs_user_id, username, display_name) "
        "VALUES (%s,'D1','dr1','dr. Uji') RETURNING id", (cl,)).fetchone()[0]
    se = c.execute(
        "INSERT INTO consult_sessions(client_id, user_id, no_rawat, consent_at, consent_by) "
        "VALUES (%s,%s,'2026/01/01/000001', now(), 'perawat') RETURNING id", (cl, dr)).fetchone()[0]
    return cl, dr, se


def test_extensions_present(conn):
    names = {r[0] for r in conn.execute("SELECT extname FROM pg_extension")}
    assert {"pg_trgm", "vector"} <= names


def test_consent_required(conn):
    cl, dr, _ = _seed(conn)
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute(
            "INSERT INTO consult_sessions(client_id, user_id, no_rawat, consent_by) "
            "VALUES (%s,%s,'X','p')", (cl, dr))


def test_ai_soap_cannot_be_approved(conn):
    cl, dr, se = _seed(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO soap_notes(client_id, session_id, version, source, approved_by, approved_at) "
            "VALUES (%s,%s,1,'ai',%s, now())", (cl, se, dr))


def test_cannot_submit_unapproved_soap(conn):
    cl, dr, se = _seed(conn)
    soap = conn.execute(
        "INSERT INTO soap_notes(client_id, session_id, version, source, created_by) "
        "VALUES (%s,%s,1,'dokter',%s) RETURNING id", (cl, se, dr)).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "INSERT INTO simrs_submissions(client_id, session_id, soap_id, adapter, status) "
            "VALUES (%s,%s,%s,'mock','pending')", (cl, se, soap))


def test_can_submit_approved_soap(conn):
    cl, dr, se = _seed(conn)
    soap = conn.execute(
        "INSERT INTO soap_notes(client_id, session_id, version, source, created_by, approved_by, approved_at) "
        "VALUES (%s,%s,1,'dokter',%s,%s, now()) RETURNING id", (cl, se, dr, dr)).fetchone()[0]
    conn.execute(
        "INSERT INTO simrs_submissions(client_id, session_id, soap_id, adapter, status) "
        "VALUES (%s,%s,%s,'mock','pending')", (cl, se, soap))


def test_audit_log_is_append_only(conn):
    conn.execute("INSERT INTO audit_log(actor_type, action) VALUES ('system','uji')")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE audit_log SET action='ubah'")
    conn.rollback()
    conn.execute("INSERT INTO audit_log(actor_type, action) VALUES ('system','uji')")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM audit_log")


def test_terminology_trgm_and_unique(conn):
    sid = conn.execute(
        "INSERT INTO terminology_systems(code, version, source_url) "
        "VALUES ('UJI','0','uji://') RETURNING id").fetchone()[0]
    conn.execute(
        "INSERT INTO terminology_codes(system_id, code, display, display_normalized) "
        "VALUES (%s,'T1','Contoh uji','contoh uji')", (sid,))
    n = conn.execute(
        "SELECT count(*) FROM terminology_codes WHERE system_id=%s "
        "AND display_normalized %% 'contoh ujj'", (sid,)).fetchone()[0]
    assert n == 1
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO terminology_codes(system_id, code, display, display_normalized) "
            "VALUES (%s,'T1','dup','dup')", (sid,))
