"""Harness evaluasi ekstraksi + validator.

  python -m evaluation.run_eval --models qwen2.5:3b-instruct-q4_K_M,qwen2.5:7b-instruct-q4_K_M
  python -m evaluation.run_eval --replay evaluation/results/<model>_raw.json   (tanpa LLM)

Membandingkan model LLM pada data yang SAMA; pilih model berdasarkan precision di field berisiko
(obat, dosis, alergi, diagnosis) pada tampilan 'lolos'/'diterima', bukan kesan umum.
PERINGATAN: kasus bawaan adalah SIMULASI, belum dianotasi dokter."""
import argparse
import json
import re
import sys
from pathlib import Path

from app import extraction, llm, vocab
from app.validator import Segment, validate_all

from .metrics import RISKY, aggregate, evaluate_case

HERE = Path(__file__).parent


def load_cases(path: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))]


def run_case(case: dict, model: str | None, raw_override: str | None = None) -> tuple[dict, str]:
    segs = [Segment(i, s["start_ms"], s["end_ms"], s["speaker"], s["text"]) for i, s in enumerate(case["segments"])]
    if raw_override is not None:
        raw = raw_override
        try:
            items, dropped = extraction.parse_llm_json(raw)
            res = {"items": items, "dropped": dropped, "manual": False}
        except extraction.ParseError:
            res = {"items": [], "dropped": 0, "manual": True}
    else:
        captured = {}
        orig = llm.call_llm

        def spy(*a, **k):
            captured["raw"] = orig(*a, **k)
            return captured["raw"]
        llm.call_llm = spy
        try:
            res = extraction.extract(segs, model=model)
        finally:
            llm.call_llm = orig
        raw = captured.get("raw", "")
    val = validate_all(res["items"], segs, vocab.drug_names(), vocab.vocab_terms(), res["dropped"])
    cr = evaluate_case(res["items"], val, case["gold"])
    cr["parse_failed"] = res["manual"]
    cr["id"] = case["id"]
    return cr, raw


def fmt(x):
    return "  - " if x is None else f"{x:.2f}"


def report(model: str, summary: dict) -> str:
    lines = [f"### Model: {model}", "", "| field | tampilan | TP | FP | FN | precision | recall |",
             "|---|---|---|---|---|---|---|"]
    for f in RISKY:
        for view in ("mentah", "lolos", "diterima"):
            s = summary[view].get(f, {"tp": 0, "fp": 0, "fn": 0, "precision": None, "recall": None})
            lines.append(f"| **{f}** | {view} | {s['tp']} | {s['fp']} | {s['fn']} | {fmt(s['precision'])} | {fmt(s['recall'])} |")
    r = summary["_ringkasan"]
    lines += ["", f"- kasus: {r['kasus']}  | JSON gagal: {r['kasus_json_gagal']}  | kualitas rendah: {r['kasus_kualitas_rendah']}",
              f"- tingkat bukti ditolak validator: {r['tingkat_bukti_ditolak']:.2%}  | ditandai: {r['tingkat_ditandai']:.2%}",
              f"- tingkat omisi vs gold (tampilan lolos): {fmt(r['tingkat_omisi_vs_gold'])}  | rata-rata 'terlewat'/kasus: {r['rata2_terlewat_per_kasus']:.2f}", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "cases"))
    ap.add_argument("--models", default="")
    ap.add_argument("--replay", help="JSON {case_id: raw_reply}; nama model diambil dari nama file")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    cases = load_cases(Path(a.cases))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.replay:
        targets = [("replay:" + Path(a.replay).stem, json.loads(Path(a.replay).read_text(encoding="utf-8")))]
    else:
        targets = [(m, None) for m in a.models.split(",") if m]
    if not targets:
        print("Isi --models atau --replay", file=sys.stderr)
        return 2
    reports = []
    for model, replay in targets:
        results, raws = [], {}
        for c in cases:
            cr, raw = run_case(c, None if replay else model, replay.get(c["id"]) if replay else None)
            results.append(cr)
            raws[c["id"]] = raw
        summary = aggregate(results)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", model)
        (out / f"{safe}_raw.json").write_text(json.dumps(raws, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{safe}_summary.json").write_text(
            json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=1), encoding="utf-8")
        reports.append(report(model, summary))
    md = "\n".join(reports)
    (out / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
