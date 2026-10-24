"""Evaluasi pemetaan kode terhadap anotasi koder (retrieve -> pilih -> validasi), butuh DB + LLM + tabel termuat.

  python -m evaluation.code_eval [--model qwen2.5:3b-instruct-q4_K_M] [--cases evaluation/code_cases.json]

Metrik: recall kandidat (kode benar ada di daftar kandidat), akurasi usulan, presisi 'terisi' (yang diisi otomatis),
tingkat saran/kosong. Isi 'expected' harus dari koder RS; bawaan hanya SIMULASI."""
import argparse
import json
from pathlib import Path

from app import llm
from app.config import get_settings
from app.db import engine
from app.terminology import mapper, retrieve

HERE = Path(__file__).parent


def summarize(rows: list[dict]) -> dict:
    lab = [r for r in rows if r["expected"]]
    filled = [r for r in rows if r["state"] == "terisi"]
    return {
        "kasus": len(rows), "berlabel": len(lab),
        "recall_kandidat": sum(r["expected"] in r["cand_codes"] for r in lab) / len(lab) if lab else None,
        "akurasi_usulan": sum(r["suggested"] == r["expected"] for r in lab) / len(lab) if lab else None,
        "presisi_terisi": (sum(r["suggested"] == r["expected"] for r in filled if r["expected"]) /
                           len([r for r in filled if r["expected"]])) if [r for r in filled if r["expected"]] else None,
        "terisi_salah": [r["term"] for r in filled if r["expected"] and r["suggested"] != r["expected"]],
        "persen_terisi": len(filled) / len(rows) if rows else None,
        "persen_saran": sum(r["state"] == "saran" for r in rows) / len(rows) if rows else None,
        "persen_kosong": sum(r["state"] == "kosong" for r in rows) / len(rows) if rows else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "code_cases.json"))
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-vectors", action="store_true")
    a = ap.parse_args(argv)
    s = get_settings()
    cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))["cases"]

    def retrieve_fn(system, queries, k):
        with engine().begin() as c:
            return retrieve.retrieve(c, system, queries, k, use_vectors=not a.no_vectors)

    def exists_fn(system, code):
        with engine().begin() as c:
            return retrieve.code_exists(c, system, code)

    rows = []
    for c in cases:
        item = {"teks": c["term"], "evidence": c["evidence"], "status": "dinyatakan_dokter", "verdict": "diterima", "reasons": []}
        r = mapper.map_diagnosis(item, system="ICD10", retrieve_fn=retrieve_fn, exists_fn=exists_fn,
                                 llm_fn=lambda sy, us: llm.call_llm(sy, us, json_mode=True, model=a.model),
                                 k=s.map_candidates_k, translate=s.map_translate, margin=s.map_margin)
        rows.append({"term": c["term"], "expected": c["expected"], "suggested": r.suggested_code, "state": r.state,
                     "reason": r.reason, "display": r.display, "cand_codes": [x["code"] for x in r.candidates]})
        print(f"{c['term'][:38]:38} exp={str(c['expected']):6} got={str(r.suggested_code):7} {r.state:6} {r.reason or ''} | {r.display or ''}")
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
