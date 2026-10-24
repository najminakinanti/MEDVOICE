"""Pemetaan kode: retrieve -> pilih -> validasi.

LLM TIDAK PERNAH menulis kode: ia hanya memilih NOMOR dari daftar kandidat yang berasal dari tabel resmi,
lalu kode diambil dari kandidat dan divalidasi ada di tabel. Aturan klinis ditegakkan di kode."""
import json
import re
from dataclasses import dataclass, field
from typing import Callable

CONF = {"tinggi": 0.9, "sedang": 0.6, "rendah": 0.3}

FIELD_SYSTEM = {"diagnosis": "ICD10", "obat": "KFA", "penunjang": "LOINC", "tindakan": "ICD9CM"}
SYSTEM_LABEL = {"ICD10": "diagnosis ke ICD-10", "KFA": "obat ke KFA (Kamus Farmasi dan Alat Kesehatan)",
                "LOINC": "pemeriksaan penunjang/laboratorium ke LOINC", "ICD9CM": "tindakan/prosedur ke ICD-9-CM"}

SELECT_TEMPLATE = """Anda membantu pengodean __LABEL__. Diberikan butir dari dokter dan daftar KANDIDAT bernomor
dari tabel resmi. Pilih SATU nomor kandidat yang paling cocok, atau null bila tidak ada yang cocok.
ATURAN: jangan menulis kode sendiri, hanya nomor. Jangan memilih kandidat yang lebih spesifik daripada yang disebutkan dokter
(mis. komplikasi/lokasi/kekuatan/bentuk sediaan yang tidak disebut). Jangan menebak: bila ragu, keyakinan "rendah" atau null.
Keluaran HANYA JSON: {"pilihan": <nomor atau null>, "keyakinan": "tinggi|sedang|rendah"}"""

TRANSLATE_SYSTEM = """Terjemahkan istilah medis berbahasa Indonesia ke istilah medis bahasa Inggris baku.
Gunakan ejaan Inggris Britania seperti ICD-10 (diarrhoea, oedema, anaemia). Jangan menambah informasi. Keluaran HANYA JSON: {"en": "..."}"""
SELECT_SYSTEM = SELECT_TEMPLATE.replace("__LABEL__", SYSTEM_LABEL["ICD10"])   # kompatibilitas


@dataclass
class MapResult:
    state: str                          # terisi | saran | kosong
    reason: str | None = None
    suggested_code: str | None = None
    display: str | None = None
    confidence: float | None = None
    candidates: list[dict] = field(default_factory=list)


def eligibility(item: dict, field: str = "diagnosis") -> tuple[str | None, bool]:
    """Aturan klinis. Return (alasan_tidak_dikodekan | None, hanya_saran)."""
    if item["verdict"] == "ditolak":
        return "ditolak_validator", False
    st = item["status"]
    if field == "diagnosis":
        if st == "dinegasi":
            return "dinegasi_tidak_dikodekan", False
        if st == "direncanakan":
            return "direncanakan_tidak_dikodekan", False
        if st == "dilaporkan_pasien":
            return "bukan_diagnosis_dokter", False
        if "dugaan_bukan_diagnosis_pasti" in item.get("reasons", []):
            return "dugaan_tidak_dikodekan", False
    elif field == "obat":
        if st == "dinegasi":
            return "obat_tidak_dipakai_penanganan_khusus", False      # obat yang disebut "tidak dipakai" tidak dikodekan
        if st in ("dilaporkan_pasien", "direncanakan"):
            return None, True                                          # riwayat/rencana obat: hanya saran
    elif field == "tindakan":
        if st == "dinegasi":
            return "tindakan_tidak_dilakukan", False
        if st == "direncanakan":
            return "direncanakan_tidak_dikodekan_sebagai_tindakan", False
        if st == "dilaporkan_pasien":
            return "bukan_tindakan_dokter", False
    elif field == "penunjang":
        if st == "dinegasi":
            return "pemeriksaan_tidak_dilakukan", False
        if st == "direncanakan":
            return None, True                                          # pemeriksaan direncanakan: hanya saran
    else:
        return "field_tidak_dikodekan", False
    return None, False


def _json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    return d if isinstance(d, dict) else {}


def parse_choice(raw: str, n: int) -> tuple[int | None, str]:
    """Return (indeks 0-based atau None, keyakinan). Nomor di luar rentang = tidak ada."""
    d = _json(raw)
    pil, kk = d.get("pilihan"), d.get("keyakinan")
    kk = kk if kk in CONF else "rendah"
    if isinstance(pil, bool) or not isinstance(pil, int) or not (1 <= pil <= n):
        return None, kk
    return pil - 1, kk


def build_choice_prompt(item: dict, cands: list[dict]) -> str:
    lines = "\n".join(f"{i}. {c['code']} - {c['display']}" for i, c in enumerate(cands, 1))
    return f"Butir dokter: {item['teks']}\nKutipan: \"{item['evidence']}\"\n\nKANDIDAT:\n{lines}"


def _queries(item: dict, field: str, llm_fn: Callable, translate: bool) -> list[str]:
    if field == "obat":
        base = " ".join(x for x in (item.get("nama"), item.get("dosis")) if x) or item["teks"]
        return [base] + ([item["nama"]] if item.get("nama") and item.get("dosis") else [])
    qs = [item["teks"]]
    if translate:
        en = _json(llm_fn(TRANSLATE_SYSTEM, item["teks"])).get("en")
        if isinstance(en, str) and en.strip():
            qs.append(en.strip()[:200])
    return qs


def map_item(item: dict, *, field: str, retrieve_fn: Callable, llm_fn: Callable, exists_fn: Callable,
             k: int = 8, translate: bool = True, margin: float = 0.05) -> MapResult:
    system = FIELD_SYSTEM[field]
    why, only_suggest = eligibility(item, field)
    if why:
        return MapResult("kosong", why)
    cands = retrieve_fn(system, _queries(item, field, llm_fn, translate), k)
    if not cands:
        return MapResult("kosong", "tidak_ada_kandidat")
    select_system = SELECT_TEMPLATE.replace("__LABEL__", SYSTEM_LABEL[system])
    idx, kk = parse_choice(llm_fn(select_system, build_choice_prompt(item, cands)), len(cands))
    if idx is None:
        return MapResult("kosong", "llm_tidak_ada_yang_cocok", candidates=cands)
    chosen = cands[idx]
    real = exists_fn(system, chosen["code"])           # validasi: kode HARUS ada di tabel
    if not real:
        return MapResult("kosong", "kode_tidak_ada_di_tabel", candidates=cands)
    conf = CONF[kk]
    top_two = sorted(cands, key=lambda c: -c.get("sim", 0))[:2]
    ambiguous = len(top_two) > 1 and (top_two[0].get("sim", 0) - top_two[1].get("sim", 0)) < margin
    if idx != 0 or kk != "tinggi" or ambiguous or item["verdict"] != "diterima" or only_suggest:
        reason = ("keyakinan_rendah" if kk != "tinggi" else
                  "kandidat_mirip" if ambiguous else
                  "bukan_peringkat_pertama" if idx != 0 else
                  "butir_ditandai" if item["verdict"] != "diterima" else "status_hanya_saran")
        return MapResult("saran", reason, chosen["code"], real["display"], conf, cands)
    return MapResult("terisi", None, chosen["code"], real["display"], conf, cands)


def map_diagnosis(item: dict, *, system: str = "ICD10", **kw) -> MapResult:
    return map_item(item, field="diagnosis", **kw)
