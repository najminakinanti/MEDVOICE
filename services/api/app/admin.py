"""CLI admin: python -m app.admin <perintah>. Kunci API hanya ditampilkan SEKALI saat dibuat."""
import argparse
import getpass
import sys

from sqlalchemy import text

from . import security
from .audit import audit
from .config import get_settings, require_secrets
from .db import engine


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-client")
    c.add_argument("name")
    c.add_argument("--origin", action="append", default=[])
    c.add_argument("--rate-limit", type=int, default=60)
    c.add_argument("--quota", type=int)
    c.add_argument("--adapter", default="mock")
    k = sub.add_parser("create-key")
    k.add_argument("client")
    k.add_argument("--label")
    r = sub.add_parser("revoke-key")
    r.add_argument("prefix")
    d = sub.add_parser("create-doctor")
    d.add_argument("client")
    d.add_argument("username")
    d.add_argument("simrs_user_id")
    d.add_argument("display_name")
    d.add_argument("--password-env", help="nama env var berisi password; kosong = prompt")
    w = sub.add_parser("set-webhook")
    w.add_argument("client")
    w.add_argument("url")
    ws = sub.add_parser("webhook-secret")
    ws.add_argument("client")
    sub.add_parser("purge")
    a = ap.parse_args(argv)
    require_secrets(get_settings())

    with engine().begin() as conn:
        def client_id(name):
            cid = conn.execute(text("SELECT id FROM clients WHERE name=:n"), dict(n=name)).scalar()
            if not cid:
                sys.exit("client tidak ditemukan")
            return cid

        if a.cmd == "create-client":
            cid = conn.execute(text(
                "INSERT INTO clients(name, allowed_origins, rate_limit_per_min, monthly_quota, simrs_adapter) "
                "VALUES (:n,:o,:r,:q,:a) RETURNING id"),
                dict(n=a.name, o=a.origin, r=a.rate_limit, q=a.quota, a=a.adapter)).scalar()
            audit(conn, action="admin.create_client", actor_type="system", client_id=cid)
            print("client dibuat:", cid)
        elif a.cmd == "create-key":
            cid = client_id(a.client)
            key, prefix, h = security.new_api_key()
            conn.execute(text("INSERT INTO api_keys(client_id, key_prefix, key_hash, label) VALUES (:c,:p,:h,:l)"),
                         dict(c=cid, p=prefix, h=h, l=a.label))
            audit(conn, action="admin.create_key", actor_type="system", client_id=cid, after={"prefix": prefix})
            print("API KEY (simpan sekarang, tidak bisa ditampilkan lagi):", key)
        elif a.cmd == "revoke-key":
            n = conn.execute(text("UPDATE api_keys SET revoked_at=now() WHERE key_prefix=:p AND revoked_at IS NULL"),
                             dict(p=a.prefix)).rowcount
            print("dicabut:", n)
        elif a.cmd == "create-doctor":
            import os
            cid = client_id(a.client)
            pw = os.environ.get(a.password_env) if a.password_env else getpass.getpass("Password: ")
            if not pw or len(pw) < 10:
                sys.exit("password minimal 10 karakter")
            did = conn.execute(text(
                "INSERT INTO doctors(client_id, simrs_user_id, username, password_hash, display_name) "
                "VALUES (:c,:s,:u,:p,:n) RETURNING id"),
                dict(c=cid, s=a.simrs_user_id, u=a.username, p=security.hash_password(pw), n=a.display_name)).scalar()
            audit(conn, action="admin.create_doctor", actor_type="system", client_id=cid, entity="doctors", entity_id=did)
            print("dokter dibuat:", did)
        elif a.cmd == "set-webhook":
            cid = client_id(a.client)
            conn.execute(text("UPDATE clients SET webhook_url=:u WHERE id=:c"), dict(u=a.url, c=cid))
            audit(conn, action="admin.set_webhook", actor_type="system", client_id=cid, after={"url": a.url})
            print("webhook diatur")
        elif a.cmd == "webhook-secret":
            print("Rahasia webhook (HMAC-SHA256 atas timestamp.body):", security.webhook_secret(str(client_id(a.client))))
        elif a.cmd == "purge":
            from .soap_pipeline import purge_expired
            print(purge_expired())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
