"""Penyusun SOAP dari butir yang lolos validator. Kode biasa (tanpa LLM).
Tiap kalimat tertaut ke butir sumber (-> kutipan bukti). Butir ditolak tidak dipakai."""
from dataclasses import dataclass, field

SECTION_OF = {
    "keluhan_utama": "S", "keluhan_lain": "S", "riwayat": "S", "alergi": "S",
    "tanda_vital": "O", "pemeriksaan_fisik": "O", "penunjang": "O",
    "diagnosis": "A",
    "obat": "P", "tindakan": "P", "edukasi": "P", "rencana": "P",
}
FIELD_ORDER = list(SECTION_OF)
FIELD_LABEL = {
    "keluhan_utama": "Keluhan utama", "keluhan_lain": "Keluhan lain", "riwayat": "Riwayat",
    "alergi": "Alergi", "tanda_vital": "Tanda vital", "pemeriksaan_fisik": "Pemeriksaan fisik",
    "penunjang": "Penunjang", "diagnosis": "Diagnosis", "obat": "Obat", "tindakan": "Tindakan",
    "edukasi": "Edukasi", "rencana": "Rencana",
}
EMPTY_TEXT = "Tidak disebutkan"


@dataclass
class SoapItem:
    id: str
    field: str
    status: str
    teks: str
    nama: str | None
    dosis: str | None
    verdict: str
    reasons: list[str]


@dataclass
class Sentence:
    section: str
    idx: int
    text: str
    evidence_item_ids: list[str] = field(default_factory=list)
    is_ai_suspicion: bool = False
    flagged: bool = False


def _core(it: SoapItem) -> str:
    if it.field == "obat":
        base = " ".join(x for x in (it.nama, it.dosis) if x) or it.teks
        if not it.dosis and not any(ch.isdigit() for ch in base):      # angka ada di teks = dosis tersebut
            base += " (dosis tidak disebutkan)"
        return base
    return it.teks or (it.nama or "")


def sentence_for(it: SoapItem) -> Sentence:
    core = _core(it)
    label = FIELD_LABEL[it.field]
    suspicion = False
    if it.field == "diagnosis":
        if "dugaan_bukan_diagnosis_pasti" in it.reasons:
            text, suspicion = f"[Dugaan, bukan diagnosis pasti] {core}", True
        elif it.status == "dinegasi":
            text = f"Disingkirkan dokter: {core}"
        else:
            text = core
    elif it.status == "dinegasi":
        text = f"{label}: menyangkal/tidak ada - {core}"
    elif it.status == "direncanakan":
        text = f"{label} (direncanakan, belum dilakukan): {core}"
    elif it.status == "dilaporkan_pasien":
        text = f"{label} (dilaporkan pasien): {core}"
    else:
        text = f"{label}: {core}"
    return Sentence(SECTION_OF[it.field], 0, text, [it.id], suspicion, it.verdict == "ditandai")


def compose(items: list[SoapItem]) -> list[Sentence]:
    usable = [i for i in items if i.verdict in ("diterima", "ditandai") and i.field in SECTION_OF]
    usable.sort(key=lambda i: FIELD_ORDER.index(i.field))
    out: list[Sentence] = []
    for sec in "SOAP":
        sec_items = [sentence_for(i) for i in usable if SECTION_OF[i.field] == sec]
        if sec == "A":     # diagnosis pasti dulu, dugaan di bawah dan berlabel
            sec_items.sort(key=lambda s: s.is_ai_suspicion)
        if not sec_items:
            sec_items = [Sentence(sec, 0, EMPTY_TEXT)]
        for n, s in enumerate(sec_items):
            s.idx = n
            out.append(s)
    return out
