import ipaddress
import json

from sqlalchemy import text


def _valid_ip(ip):
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def audit(conn, *, action, actor_type, actor_id=None, client_id=None, session_id=None,
          entity=None, entity_id=None, before=None, after=None, ip=None):
    """Tulis audit log. before/after hanya metadata (id, versi, jumlah) - JANGAN isi transkrip."""
    conn.execute(
        text("INSERT INTO audit_log(client_id, actor_type, actor_id, session_id, action, entity, "
             "entity_id, before, after, ip) VALUES (:c,:at,:ai,:s,:a,:e,:ei,"
             "CAST(:b AS jsonb),CAST(:af AS jsonb),CAST(:ip AS inet))"),
        dict(c=client_id, at=actor_type, ai=actor_id and str(actor_id), s=session_id, a=action,
             e=entity, ei=entity_id and str(entity_id),
             b=json.dumps(before) if before is not None else None,
             af=json.dumps(after) if after is not None else None, ip=_valid_ip(ip)),
    )
