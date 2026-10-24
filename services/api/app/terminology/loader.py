"""Memuat tabel kode resmi ke DB. Sumber, versi, dan checksum dicatat di terminology_systems.

  python -m app.terminology.loader icd10 data/icd10_who/x/icd102019en.xml --source-url URL [--embed]
Embedding bisa dijalankan terpisah dan dilanjutkan (hanya baris tanpa embedding)."""
import argparse
import hashlib
import sys
import time

from sqlalchemy import text

from ..db import engine
from ..embeddings import embed, to_pgvector
from ..validator import normalize
from .claml import parse_claml


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_codes(conn, system: str, version: str, source_url: str, checksum: str | None, rows: list[dict]) -> int:
    """rows: {code, display, search_text, attrs}. Idempoten per (system, version)."""
    sid = conn.execute(text(
        "INSERT INTO terminology_systems(code, version, source_url, checksum) VALUES (:c,:v,:u,:h) "
        "ON CONFLICT (code, version) DO UPDATE SET source_url=EXCLUDED.source_url, checksum=EXCLUDED.checksum, "
        "loaded_at=now() RETURNING id"), dict(c=system, v=version, u=source_url, h=checksum)).scalar()
    conn.execute(text("DELETE FROM terminology_codes WHERE system_id=:s"), dict(s=sid))
    conn.execute(text(
        "INSERT INTO terminology_codes(system_id, code, display, display_normalized, search_text, attrs) "
        "VALUES (:s,:c,:d,:dn,:st,CAST(:a AS jsonb))"),
        [dict(s=sid, c=r["code"], d=r["display"], dn=normalize(r["display"]), st=r["search_text"],
              a=__import__("json").dumps(r.get("attrs", {}))) for r in rows])
    return sid


def icd10_rows(path: str) -> tuple[list[dict], dict]:
    entries, meta = parse_claml(path)
    rows = []
    for e in entries:
        parts = [e.context, e.display] + e.inclusions
        rows.append({"code": e.code, "display": e.display,
                     "search_text": normalize(" . ".join(p for p in parts if p)),
                     "attrs": {"parent": e.parent_code, "inclusions": e.inclusions[:8]}})
    return rows, meta


def csv_rows(path: str, code_col: str, display_col: str, extra_cols: list[str], encoding: str = "utf-8-sig",
             delimiter: str = ",") -> list[dict]:
    """Tabel generik dari CSV (LOINC: Loinc.csv, KFA/KPTL: ekspor resmi). Kolom dipetakan lewat argumen;
    tidak ada nama kolom 'resmi' yang diasumsikan di sini."""
    import csv
    rows, seen = [], set()
    with open(path, encoding=encoding, newline="") as f:
        for r in csv.DictReader(f, delimiter=delimiter):
            code, disp = (r.get(code_col) or "").strip(), (r.get(display_col) or "").strip()
            if not code or not disp or code in seen:
                continue
            seen.add(code)
            extra = {c: (r.get(c) or "").strip() for c in extra_cols if r.get(c)}
            rows.append({"code": code, "display": disp,
                         "search_text": normalize(" . ".join([disp] + list(extra.values()))), "attrs": extra})
    return rows


def embed_missing(system_id: int, batch: int = 32, limit: int | None = None) -> int:
    done = 0
    while True:
        with engine().begin() as c:
            todo = c.execute(text(
                "SELECT id, display, search_text FROM terminology_codes WHERE system_id=:s AND embedding IS NULL "
                "ORDER BY id LIMIT :n"), dict(s=system_id, n=batch)).all()
        if not todo or (limit and done >= limit):
            return done
        vecs = embed([f"{d}. {st}"[:600] for _, d, st in todo])
        with engine().begin() as c:
            for (i, _, _), v in zip(todo, vecs):
                c.execute(text("UPDATE terminology_codes SET embedding=CAST(:v AS vector) WHERE id=:i"),
                          dict(v=to_pgvector(v), i=i))
        done += len(todo)
        if done % (batch * 10) == 0:
            print(f"embedded {done}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("system", choices=["icd10", "loinc", "kfa", "icd9cm", "kptl"])
    ap.add_argument("path")
    ap.add_argument("--version", help="wajib untuk sistem selain icd10")
    ap.add_argument("--code-col")
    ap.add_argument("--display-col")
    ap.add_argument("--extra-cols", default="")
    ap.add_argument("--delimiter", default=",")
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--embed-only", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    sysname = a.system.upper()
    if not a.embed_only:
        if a.system == "icd10":
            rows, meta = icd10_rows(a.path)
            version = meta["version"] or "unknown"
        else:
            if not (a.version and a.code_col and a.display_col):
                sys.exit("--version, --code-col, --display-col wajib untuk sistem ini")
            rows = csv_rows(a.path, a.code_col, a.display_col, [c for c in a.extra_cols.split(",") if c], delimiter=a.delimiter)
            version = a.version
        with engine().begin() as c:
            sid = load_codes(c, sysname, version, a.source_url, sha256_file(a.path), rows)
        print(f"dimuat {len(rows)} kode {sysname} versi {version} (system_id={sid}) {time.time() - t0:.1f}s")
    else:
        with engine().begin() as c:
            sid = c.execute(text("SELECT id FROM terminology_systems WHERE code=:c ORDER BY loaded_at DESC LIMIT 1"),
                            dict(c=sysname)).scalar()
    if a.embed or a.embed_only:
        n = embed_missing(sid)
        print(f"embedding selesai: {n} baris, {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
