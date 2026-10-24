"""Validator klinis. KODE BIASA, bukan LLM. Tidak ada I/O di modul ini.

Keluaran per butir: diterima | ditandai | ditolak, plus alasan (kode). Waktu/segmen bukti
dihitung ulang dari transkrip oleh kode, bukan dipercaya dari LLM.
"""
import re
import unicodedata
from dataclasses import dataclass, field

KNOWN_FIELDS = {
    "keluhan_utama", "keluhan_lain", "riwayat", "alergi", "tanda_vital", "pemeriksaan_fisik",
    "penunjang", "diagnosis", "obat", "tindakan", "edukasi", "rencana",
}
STATUSES = {"dinyatakan_dokter", "dilaporkan_pasien", "dinegasi", "direncanakan"}

NEGATION = re.compile(
    r"\b(tidak|tak|belum|bukan|tanpa|menyangkal|disangkal|negatif|nggak|gak|ga|ndak|no|denies|denied|without)\b")
HEDGE = re.compile(
    r"\b(curiga|kemungkinan|suspek|suspect|dugaan|mungkin|dd|diferensial|sepertinya|kayaknya|probable|r/o|rule out)\b")
FUTURE = re.compile(r"\b(akan|nanti|rencana|rencananya|kita coba|disarankan|coba|besok|mau)\b")
PAST = re.compile(r"\b(sudah|tadi|telah|barusan|kemarin)\b")

UNITS = (r"(?:mg/dl|mmol/l|mmhg|mg|mcg|µg|ug|gr|g|ml|iu|ui|unit|tablet|tab|kapsul|kaps|sdm|sdt|"
         r"tetes|puff|kali|x|cm|kg|bpm|%|°c|celcius|derajat|/menit|menit|hari|jam)")
NUMBER_UNIT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:/\d+)?\s*" + UNITS + r"(?!\w)")
DOSE_FORMAT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|gr|g|ml|iu|ui|unit|tablet|tab|kapsul|kaps|sdm|sdt|tetes|puff)(?!\w)")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)
    s = re.sub(r"[^\w/%.°µ ]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Segment:
    idx: int
    start_ms: int
    end_ms: int
    speaker: str
    text: str


@dataclass
class Item:
    field: str
    status: str
    evidence: str
    segment_idxs: list[int]
    teks: str = ""
    nama: str | None = None
    dosis: str | None = None


@dataclass
class ItemResult:
    verdict: str                       # diterima | ditandai | ditolak
    reasons: list[str] = field(default_factory=list)
    segment_idxs: list[int] = field(default_factory=list)
    start_ms: int = 0
    end_ms: int = 0
    span: tuple[int, int] | None = None   # posisi karakter di teks gabungan ternormalisasi


@dataclass
class Missed:
    kind: str                          # obat | angka_satuan | istilah_vocab
    mention: str
    segment_idx: int
    start_ms: int
    end_ms: int


class Transcript:
    """Teks gabungan ternormalisasi + pemetaan posisi karakter -> segmen."""

    def __init__(self, segments: list[Segment]):
        self.segments = segments
        self.norm = [normalize(s.text) for s in segments]
        self.joined = " ".join(self.norm)
        self.offsets: list[tuple[int, int]] = []
        pos = 0
        for n in self.norm:
            self.offsets.append((pos, pos + len(n)))
            pos += len(n) + 1

    def segs_for_span(self, a: int, b: int) -> list[int]:
        return [i for i, (s, e) in enumerate(self.offsets) if s < b and e > a]

    def find(self, needle: str, near: list[int] | None = None) -> tuple[int, int] | None:
        if not needle:
            return None
        for i in near or []:
            if 0 <= i < len(self.norm):
                p = self.norm[i].find(needle)
                if p >= 0:
                    s = self.offsets[i][0] + p
                    return (s, s + len(needle))
        p = self.joined.find(needle)
        return (p, p + len(needle)) if p >= 0 else None


_UNIT_WORDS = {"nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7,
               "delapan": 8, "sembilan": 9}


def _word_numbers(norm: str) -> set[str]:
    """Angka berbentuk kata Indonesia (tiga, sebelas, dua puluh lima, seratus) -> digit."""
    toks, out, i = norm.split(), set(), 0
    while i < len(toks):
        t = toks[i]
        if t == "sepuluh":
            out.add("10")
        elif t == "sebelas":
            out.add("11")
        elif t == "seratus":
            out.add("100")
        elif t in _UNIT_WORDS:
            n = _UNIT_WORDS[t]
            if i + 1 < len(toks) and toks[i + 1] == "belas":
                n, i = 10 + n, i + 1
            elif i + 1 < len(toks) and toks[i + 1] == "puluh":
                n, i = n * 10, i + 1
                if i + 1 < len(toks) and toks[i + 1] in _UNIT_WORDS and toks[i + 1] != "nol":
                    n, i = n + _UNIT_WORDS[toks[i + 1]], i + 1
            out.add(str(n))
        i += 1
    return out


def _nums(s: str) -> set[str]:
    n = normalize(s)
    return set(NUMBER.findall(n)) | _word_numbers(n)


def validate_item(item: Item, tr: Transcript) -> ItemResult:
    reasons: list[str] = []
    rejected = False
    flagged = False

    if item.field not in KNOWN_FIELDS:
        return ItemResult("ditolak", ["field_tidak_dikenal"])
    if item.status not in STATUSES:
        return ItemResult("ditolak", ["status_tidak_valid"])

    ev = normalize(item.evidence)
    if len(ev) < 3:
        return ItemResult("ditolak", ["bukti_kosong_atau_terlalu_pendek"])
    span = tr.find(ev, item.segment_idxs)
    if span is None:
        return ItemResult("ditolak", ["bukti_tidak_ada_di_transkrip"])

    idxs = tr.segs_for_span(*span)
    segs = [tr.segments[i] for i in idxs]
    res = ItemResult("diterima", reasons, [tr.segments[i].idx for i in idxs],
                     segs[0].start_ms, segs[-1].end_ms, span)
    if item.segment_idxs and not set(res.segment_idxs) & set(item.segment_idxs):
        reasons.append("segmen_dari_llm_salah_dikoreksi_kode")
        flagged = True

    # --- angka harus ada di bukti ---
    value_text = " ".join(x for x in (item.teks, item.dosis or "", item.nama or "") if x)
    if _nums(value_text) - _nums(item.evidence):
        if item.field == "obat":
            rejected = True
            reasons.append("angka_dosis_tidak_ada_di_bukti")
        else:
            flagged = True
            reasons.append("angka_tidak_ada_di_bukti")

    # --- obat: nama harus ada di bukti; format dosis ---
    if item.field == "obat":
        if item.nama and normalize(item.nama) not in ev:
            rejected = True
            reasons.append("nama_obat_tidak_ada_di_bukti")
        if item.dosis:
            if not DOSE_FORMAT.search(normalize(item.dosis)):
                flagged = True
                reasons.append("format_dosis_tidak_dikenal")
        elif DOSE_FORMAT.search(ev):
            flagged = True
            reasons.append("bukti_memuat_dosis_tapi_dosis_kosong")

    # --- siapa yang mengucapkan: pertanyaan dokter bukan keluhan pasien (hanya bila pembicara diketahui) ---
    speakers_all = {x.speaker for x in segs}
    if item.field != "diagnosis":
        if item.status == "dilaporkan_pasien" and speakers_all == {"dokter"}:
            flagged = True
            reasons.append("dilaporkan_pasien_tapi_diucapkan_dokter")
        elif item.status == "dinyatakan_dokter" and speakers_all == {"pasien"}:
            flagged = True
            reasons.append("dinyatakan_dokter_tapi_diucapkan_pasien")

    # --- negasi vs status ---
    has_neg = bool(NEGATION.search(ev))
    if item.status == "dinegasi" and not has_neg:
        flagged = True
        reasons.append("status_dinegasi_tanpa_kata_negasi")
    if item.status != "dinegasi" and has_neg:
        flagged = True
        reasons.append("bukti_memuat_negasi_tapi_status_bukan_dinegasi")

    # --- diagnosis hanya sah bila diucapkan dokter ---
    if item.field == "diagnosis":
        speakers = {s.speaker for s in segs}
        if "pasien" in speakers and "dokter" not in speakers:
            rejected = True
            reasons.append("diagnosis_diucapkan_pasien")
        elif "dokter" not in speakers:
            flagged = True
            reasons.append("pembicara_tidak_diketahui_dokter_harus_konfirmasi")
        if item.status == "dilaporkan_pasien":
            rejected = True
            reasons.append("diagnosis_status_dilaporkan_pasien")
        if HEDGE.search(ev):
            flagged = True
            reasons.append("dugaan_bukan_diagnosis_pasti")
        content = [w for w in normalize(item.teks).split() if len(w) >= 4]
        if content and not any(w in ev for w in content):
            flagged = True
            reasons.append("istilah_diagnosis_tidak_ada_di_bukti")

    # --- rencana vs sudah dilakukan ---
    if item.field in {"tindakan", "obat"}:
        if item.status == "dinyatakan_dokter" and FUTURE.search(ev):
            flagged = True
            reasons.append("bukti_bernada_rencana_status_dinyatakan")
        if item.status == "direncanakan" and PAST.search(ev) and not FUTURE.search(ev):
            flagged = True
            reasons.append("bukti_bernada_lampau_status_direncanakan")

    res.verdict = "ditolak" if rejected else ("ditandai" if flagged else "diterima")
    return res


def find_missed(tr: Transcript, covered: list[tuple[int, int]], drugs: list[str],
                vocab: list[str]) -> list[Missed]:
    """Sebutan di transkrip (obat, angka+satuan, istilah vocab) yang tak tertutup butir mana pun."""
    def is_covered(a: int, b: int) -> bool:
        return any(a >= s and b <= e for s, e in covered)

    out: dict[tuple, Missed] = {}

    def add(kind: str, a: int, b: int):
        if is_covered(a, b):
            return
        seg_i = tr.segs_for_span(a, b)
        if not seg_i:
            return
        sg = tr.segments[seg_i[0]]
        mention = tr.joined[a:b]
        out[(kind, mention, sg.idx)] = Missed(kind, mention, sg.idx, sg.start_ms, sg.end_ms)

    for m in NUMBER_UNIT.finditer(tr.joined):
        add("angka_satuan", m.start(), m.end())
    for kind, terms in (("obat", drugs), ("istilah_vocab", vocab)):
        for t in terms:
            nt = normalize(t)
            if not nt:
                continue
            for m in re.finditer(r"(?<!\w)" + re.escape(nt) + r"(?!\w)", tr.joined):
                add(kind, m.start(), m.end())
    return sorted(out.values(), key=lambda x: (x.start_ms, x.mention))


def validate_all(items: list[Item], segments: list[Segment], drugs: list[str], vocab: list[str],
                 dropped: int = 0, reject_ratio: float = 0.3) -> dict:
    tr = Transcript(segments)
    results = [validate_item(it, tr) for it in items]
    covered = [r.span for r in results if r.verdict != "ditolak" and r.span]
    missed = find_missed(tr, covered, drugs, vocab)
    total = len(items) + dropped
    rejected = sum(1 for r in results if r.verdict == "ditolak") + dropped
    low_quality = total >= 3 and rejected / total >= reject_ratio
    return {"results": results, "missed": missed, "low_quality": low_quality,
            "rejected": rejected, "total": total}
