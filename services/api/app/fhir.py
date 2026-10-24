"""Pembentuk Bundle FHIR R4 (transaction) untuk SatuSehat dari SOAP final yang sudah di-approve.

Cakupan saat ini: Composition (narasi SOAP) + Condition untuk diagnosis ber-kode ICD-10.
Kode obat (KFA)/lab (LOINC)/tindakan belum dibentuk menjadi resource sendiri.
Referensi Patient/Encounter/Practitioner (ID SatuSehat/IHS) HARUS disediakan SIMRS lewat `refs`;
engine tidak menebak atau membuatnya. Belum diuji terhadap server SatuSehat sungguhan."""
import html
import uuid
from datetime import datetime, timezone

ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10"
CONDITION_CATEGORY = "http://terminology.hl7.org/CodeSystem/condition-category"
CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"
SECTION_TITLE = {"S": "Subjective", "O": "Objective", "A": "Assessment", "P": "Plan"}
REQUIRED_REFS = ("patient", "encounter", "practitioner", "organization")


class FhirError(Exception):
    pass


def _narrative(lines: list[str]) -> dict:
    body = "".join(f"<li>{html.escape(x)}</li>" for x in lines) or "<li>Tidak disebutkan</li>"
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><ul>{body}</ul></div>'}


def build_bundle(*, soap: dict, codes: list[dict], refs: dict, when: datetime | None = None,
                 composition_type_coding: dict | None = None) -> dict:
    missing = [k for k in REQUIRED_REFS if not refs.get(k)]
    if missing:
        raise FhirError("refs_missing:" + ",".join(missing))
    when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
    entries, cond_urls = [], []
    for c in codes:
        if c.get("system") != "ICD10" or not c.get("code"):
            continue
        url = "urn:uuid:" + str(uuid.uuid4())
        cond_urls.append((url, c))
        entries.append({"fullUrl": url, "resource": {
            "resourceType": "Condition",
            "clinicalStatus": {"coding": [{"system": CONDITION_CLINICAL, "code": "active"}]},
            "category": [{"coding": [{"system": CONDITION_CATEGORY, "code": "encounter-diagnosis"}]}],
            "code": {"coding": [{"system": ICD10_SYSTEM, "code": c["code"], "display": c.get("display")}]},
            "subject": {"reference": refs["patient"]},
            "encounter": {"reference": refs["encounter"]},
            "recordedDate": when},
            "request": {"method": "POST", "url": "Condition"}})
    sections = []
    for sec in "SOAP":
        s = {"title": SECTION_TITLE[sec], "text": _narrative(soap.get(sec, []))}
        if sec == "A" and cond_urls:
            s["entry"] = [{"reference": u} for u, _ in cond_urls]
        sections.append(s)
    comp_type = {"text": "Catatan SOAP"}
    if composition_type_coding:
        comp_type["coding"] = [composition_type_coding]
    comp = {"resourceType": "Composition", "status": "final", "type": comp_type,
            "subject": {"reference": refs["patient"]}, "encounter": {"reference": refs["encounter"]},
            "date": when, "author": [{"reference": refs["practitioner"]}],
            "custodian": {"reference": refs["organization"]}, "title": "Catatan SOAP (disusun dengan bantuan AI, disetujui dokter)",
            "section": sections}
    entries.insert(0, {"fullUrl": "urn:uuid:" + str(uuid.uuid4()), "resource": comp,
                       "request": {"method": "POST", "url": "Composition"}})
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}
