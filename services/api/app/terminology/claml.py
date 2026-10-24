"""Parser ClaML (format resmi WHO ICD-10). Fungsi murni, tanpa DB.

Keluaran: daftar kode yang BISA dikodekan (daun). Kode 4/5 karakter hasil modifier WHO
(mis. E11 + .9 -> E11.9, M00.0 + 0 -> M00.00) diekspansi sesuai definisi di berkas itu sendiri;
tidak ada kode yang dibuat dari ingatan."""
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class CodeEntry:
    code: str
    display: str                       # label resmi (ditambah label modifier bila hasil ekspansi)
    parent_code: str | None = None
    context: str = ""                  # label induk (konteks pencarian)
    inclusions: list[str] = field(default_factory=list)   # sinonim/inklusi resmi WHO


def _text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def _rubrics(cls, kind: str) -> list[str]:
    return [_text(r.find("Label")) for r in cls.findall("Rubric") if r.get("kind") == kind and r.find("Label") is not None]


def parse_claml(path: str) -> tuple[list[CodeEntry], dict]:
    root = ET.parse(path).getroot()
    title = root.find("Title")
    meta = {"title": _text(title) if title is not None else "", "version": title.get("version") if title is not None else None}
    classes = {c.get("code"): c for c in root.findall("Class")}
    mod_classes = defaultdict(list)
    for m in root.findall("ModifierClass"):
        mod_classes[m.get("modifier")].append(m)

    def label(c) -> str:
        p = _rubrics(c, "preferred")
        return p[0] if p else ""

    def parent_category(c):
        for s in c.findall("SuperClass"):
            p = classes.get(s.get("code"))
            if p is not None and p.get("kind") == "category":
                return p
        return None

    entries: dict[str, CodeEntry] = {}
    expanded_parents: set[str] = set()
    for code, c in classes.items():
        if c.get("kind") != "category":
            continue
        subs = [s.get("code") for s in c.findall("SubClass") if s.get("code") in classes]
        mods = [m.get("code") for m in c.findall("ModifiedBy")]
        excluded = {e.get("code") for e in c.findall("ExcludeModifier")}
        mods = [m for m in mods if m not in excluded]
        par = parent_category(c)
        base = CodeEntry(code, label(c), par.get("code") if par is not None else None,
                         label(par) if par is not None else "", _rubrics(c, "inclusion"))
        if not subs and not mods:
            entries[code] = base                      # daun biasa (mis. I10)
        elif not subs and mods:
            for m in mods:                            # daun + modifier karakter keempat (mis. E11.x)
                for mc in mod_classes.get(m, []):
                    cc = code + mc.get("code")
                    entries[cc] = CodeEntry(cc, f"{base.display} - {label(mc)}", code, base.display, base.inclusions)
        elif subs and mods:
            for s in subs:                            # anak + modifier karakter kelima (mis. M00.0 + 0)
                sc = classes[s]
                if sc.findall("SubClass"):
                    continue
                expanded_parents.add(s)
                for m in mods:
                    for mc in mod_classes.get(m, []):
                        cc = s + mc.get("code")
                        entries[cc] = CodeEntry(cc, f"{label(sc)} - {label(mc)}", s, label(c), _rubrics(sc, "inclusion"))
    for s in expanded_parents:                        # induk yang sudah diekspansi bukan kode yang dipakai
        entries.pop(s, None)
    meta["count"] = len(entries)
    return sorted(entries.values(), key=lambda e: e.code), meta
