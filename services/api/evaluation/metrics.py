"""Metrik evaluasi (fungsi murni, ada tesnya). Fokus: precision/recall per field berisiko."""
from collections import defaultdict

from app.validator import Item, normalize

RISKY = ["obat", "dosis", "alergi", "diagnosis"]
FIELDS = ["keluhan_utama", "keluhan_lain", "riwayat", "alergi", "tanda_vital", "pemeriksaan_fisik",
          "penunjang", "diagnosis", "obat", "tindakan", "edukasi", "rencana"]


def _blob(it: Item) -> str:
    return normalize(" ".join(x for x in (it.teks, it.nama or "") if x))


def item_matches_gold(it: Item, g: dict) -> bool:
    """Cocok bila field sama, status sama (negasi/rencana harus benar), dan kata kunci gold ada."""
    if it.field != g["field"] or it.status != g["status"]:
        return False
    keys = g["key"] if isinstance(g["key"], list) else [g["key"]]     # beberapa varian kata kunci yang dianggap benar
    blob = _blob(it)
    return any(normalize(k) in blob for k in keys)


def match_field(preds: list[Item], golds: list[dict], field: str) -> tuple[int, int, int]:
    """Greedy: tiap gold dicocokkan maksimal sekali. Return (tp, fp, fn)."""
    ps = [p for p in preds if p.field == field]
    gs = [g for g in golds if g["field"] == field]
    used, tp = set(), 0
    for g in gs:
        for i, p in enumerate(ps):
            if i not in used and item_matches_gold(p, g):
                used.add(i)
                tp += 1
                break
    return tp, len(ps) - tp, len(gs) - tp


def match_dosis(preds: list[Item], golds: list[dict]) -> tuple[int, int, int]:
    """Pasangan (nama obat, dosis). Prediksi dosis yang tidak ada di gold = FP (dosis dikarang/salah)."""
    gp = [(normalize(g["nama"]), normalize(g["dosis"])) for g in golds
          if g["field"] == "obat" and g.get("dosis") and g.get("nama")]
    pp = [(normalize(p.nama), normalize(p.dosis)) for p in preds if p.field == "obat" and p.nama and p.dosis]
    remaining = list(gp)
    tp = 0
    for pair in pp:
        if pair in remaining:
            remaining.remove(pair)
            tp += 1
    return tp, len(pp) - tp, len(remaining)


def counts_for(preds: list[Item], golds: list[dict]) -> dict[str, tuple[int, int, int]]:
    out = {f: match_field(preds, golds, f) for f in FIELDS}
    out["dosis"] = match_dosis(preds, golds)
    return out


def prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return p, r


def add_counts(acc: dict, c: dict) -> None:
    for f, (tp, fp, fn) in c.items():
        a = acc.setdefault(f, [0, 0, 0])
        a[0] += tp
        a[1] += fp
        a[2] += fn


def evaluate_case(items: list[Item], validation: dict, golds: list[dict]) -> dict:
    """Tiga sudut pandang: mentah (keluaran LLM), lolos (diterima+ditandai), diterima saja."""
    verdicts = [r.verdict for r in validation["results"]]
    views = {
        "mentah": items,
        "lolos": [i for i, v in zip(items, verdicts) if v != "ditolak"],
        "diterima": [i for i, v in zip(items, verdicts) if v == "diterima"],
    }
    return {
        "counts": {name: counts_for(v, golds) for name, v in views.items()},
        "n_items": len(items),
        "n_ditolak": verdicts.count("ditolak"),
        "n_ditandai": verdicts.count("ditandai"),
        "n_terlewat": len(validation["missed"]),
        "n_gold": len(golds),
        "low_quality": validation["low_quality"],
    }


def aggregate(case_results: list[dict]) -> dict:
    views = defaultdict(dict)
    tot = defaultdict(int)
    for cr in case_results:
        for view, c in cr["counts"].items():
            add_counts(views[view], c)
        for k in ("n_items", "n_ditolak", "n_ditandai", "n_terlewat", "n_gold"):
            tot[k] += cr[k]
        tot["low_quality_cases"] += int(cr["low_quality"])
        tot["cases"] += 1
        tot["parse_failed_cases"] += int(cr.get("parse_failed", False))
    summary = {}
    for view, acc in views.items():
        summary[view] = {}
        for f, (tp, fp, fn) in acc.items():
            p, r = prf(tp, fp, fn)
            summary[view][f] = {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r}
    n = tot["n_items"] or 1
    fn_total = sum(v[2] for k, v in views.get("lolos", {}).items() if k != "dosis")
    summary["_ringkasan"] = {
        "kasus": tot["cases"],
        "tingkat_bukti_ditolak": tot["n_ditolak"] / n,
        "tingkat_ditandai": tot["n_ditandai"] / n,
        "tingkat_omisi_vs_gold": fn_total / tot["n_gold"] if tot["n_gold"] else None,
        "rata2_terlewat_per_kasus": tot["n_terlewat"] / (tot["cases"] or 1),
        "kasus_kualitas_rendah": tot["low_quality_cases"],
        "kasus_json_gagal": tot["parse_failed_cases"],
    }
    return summary


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate = (S+D+I)/N, setelah normalisasi (huruf kecil, tanpa tanda baca)."""
    r, h = normalize(reference).split(), normalize(hypothesis).split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(r)
