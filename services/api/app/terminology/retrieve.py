"""Retrieval kandidat dari tabel resmi: trigram + full-text + embedding, digabung dengan RRF."""
import re

from sqlalchemy import text

from ..embeddings import EmbeddingError, embed, to_pgvector
from ..validator import normalize


def latest_system(conn, system: str):
    return conn.execute(text("SELECT id, version FROM terminology_systems WHERE code=:c ORDER BY loaded_at DESC LIMIT 1"),
                        dict(c=system)).first()


# ICD-10 WHO memakai ejaan Inggris Britania; kueri (hasil terjemahan) sering berejaan Amerika.
UK_SPELLING = {
    "diarrhea": "diarrhoea", "edema": "oedema", "anemia": "anaemia", "hemorrhage": "haemorrhage",
    "hemoglobin": "haemoglobin", "esophagus": "oesophagus", "esophageal": "oesophageal", "pediatric": "paediatric",
    "fetal": "foetal", "hematuria": "haematuria", "ischemia": "ischaemia", "ischemic": "ischaemic",
    "leukemia": "leukaemia", "estrogen": "oestrogen", "hemorrhagic": "haemorrhagic", "hematoma": "haematoma",
    "orthopedic": "orthopaedic", "gynecologic": "gynaecological", "tumor": "tumour", "color": "colour",
    "fiber": "fibre", "hypoglycemia": "hypoglycaemia", "hyperglycemia": "hyperglycaemia", "septicemia": "septicaemia",
    "dyspnea": "dyspnoea", "diarrheal": "diarrhoeal", "anesthesia": "anaesthesia", "hemorrhoids": "haemorrhoids",
    "leukocytes": "leucocytes", "pyelonephritis": "pyelonephritis",
}


def uk_spelling(q: str) -> str:
    return " ".join(UK_SPELLING.get(w, w) for w in q.split())


def _tsquery(q: str) -> str | None:
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", normalize(q))]
    return " | ".join(dict.fromkeys(toks)) if toks else None


def retrieve(conn, system: str, queries: list[str], k: int = 8, use_vectors: bool = True) -> list[dict]:
    """Return kandidat [{code, display, rrf, trgm, vec}] terurut. Hanya kode yang ada di tabel."""
    sys_row = latest_system(conn, system)
    if not sys_row:
        return []
    sid = sys_row[0]
    scores: dict[str, dict] = {}

    def add(rank_list: list[tuple], key: str):
        for rank, (cid, code, display, val) in enumerate(rank_list):
            e = scores.setdefault(code, {"code": code, "display": display, "rrf": 0.0, "trgm": 0.0, "vec": 0.0, "fts": 0.0})
            e["rrf"] += 1.0 / (60 + rank)
            e[key] = max(e[key], float(val or 0))

    qs = [uk_spelling(normalize(q)) for q in queries if q and normalize(q)]
    for q in qs:
        rows = conn.execute(text(
            "SELECT id, code, display, GREATEST(word_similarity(:q, display_normalized), similarity(display_normalized, :q)) AS s "
            "FROM terminology_codes WHERE system_id=:s AND active AND (:q <% display_normalized OR display_normalized % :q) "
            "ORDER BY s DESC LIMIT :k"), dict(q=q, s=sid, k=k * 3)).all()
        add([tuple(r) for r in rows], "trgm")
        tq = _tsquery(q)
        if tq:
            rows = conn.execute(text(
                "SELECT id, code, display, ts_rank_cd(to_tsvector('simple', search_text), to_tsquery('simple', :tq)) AS s "
                "FROM terminology_codes WHERE system_id=:s AND active AND to_tsvector('simple', search_text) @@ to_tsquery('simple', :tq) "
                "ORDER BY s DESC LIMIT :k"), dict(tq=tq, s=sid, k=k * 3)).all()
            add([tuple(r) for r in rows], "fts")
    if use_vectors and qs:
        has_vec = conn.execute(text("SELECT 1 FROM terminology_codes WHERE system_id=:s AND embedding IS NOT NULL LIMIT 1"),
                               dict(s=sid)).first()
        if has_vec:
            try:
                for q, v in zip(qs, embed(qs)):
                    rows = conn.execute(text(
                        "SELECT id, code, display, 1 - (embedding <=> CAST(:v AS vector)) AS s FROM terminology_codes "
                        "WHERE system_id=:s AND active AND embedding IS NOT NULL ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k"),
                        dict(v=to_pgvector(v), s=sid, k=k * 3)).all()
                    add([tuple(r) for r in rows], "vec")
            except EmbeddingError:
                pass        # degradasi: tetap pakai trigram + full-text
    for e in scores.values():
        e.pop("fts", None)
    out = sorted(scores.values(), key=lambda e: -e["rrf"])[:k]
    for e in out:
        e["sim"] = max(e["trgm"], e["vec"])
    return out


def code_exists(conn, system: str, code: str) -> dict | None:
    row = conn.execute(text(
        "SELECT c.code, c.display FROM terminology_codes c JOIN terminology_systems s ON s.id=c.system_id "
        "WHERE s.id=(SELECT id FROM terminology_systems WHERE code=:sy ORDER BY loaded_at DESC LIMIT 1) "
        "AND c.code=:c AND c.active"), dict(sy=system, c=code)).first()
    return {"code": row[0], "display": row[1]} if row else None
