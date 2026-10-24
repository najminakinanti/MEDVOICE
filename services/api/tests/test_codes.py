"""Tes pemetaan kode (Fase 2). Tabel ICD-10 yang dipakai di tes integrasi adalah berkas RESMI WHO
(data/icd10_who/x/icd102019en.xml); bila tidak ada, tes integrasi dilewati."""
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.terminology import mapper
from app.terminology.claml import parse_claml
from tests.conftest import login
from tests.test_flow import GOOD_LLM, SEGMENTS, TWO_CHANNEL, fakes, record_and_finish  # noqa: F401

XML = Path(__file__).resolve().parents[3] / "data" / "icd10_who" / "x" / "icd102019en.xml"
CHOOSE_NONE = '{"pilihan": null, "keyakinan": "rendah"}'


# ------------------------------------------------------------------ unit: aturan klinis & anti-halusinasi
def item(status="dinyatakan_dokter", verdict="diterima", reasons=(), teks="hipertensi"):
    return {"teks": teks, "evidence": "diagnosisnya hipertensi", "status": status, "verdict": verdict, "reasons": list(reasons)}


CANDS = [{"code": "I10", "display": "Essential (primary) hypertension", "sim": 0.9},
         {"code": "I15.9", "display": "Secondary hypertension, unspecified", "sim": 0.5},
         {"code": "I11.9", "display": "Hypertensive heart disease without (congestive) heart failure", "sim": 0.4}]


def run(it, choice, cands=CANDS, exists=lambda s, c: {"code": c, "display": next((x["display"] for x in CANDS if x["code"] == c), "?")}):
    def llm_fn(system, user):
        return '{"en": "essential hypertension"}' if system.startswith("Terjemahkan") else choice
    return mapper.map_diagnosis(it, system="ICD10", retrieve_fn=lambda s, q, k: list(cands), llm_fn=llm_fn, exists_fn=exists)


def test_pemetaan_normal_terisi():
    r = run(item(), '{"pilihan": 1, "keyakinan": "tinggi"}')
    assert (r.state, r.suggested_code) == ("terisi", "I10")


@pytest.mark.parametrize("kw,reason", [
    (dict(status="dinegasi"), "dinegasi_tidak_dikodekan"),
    (dict(status="direncanakan"), "direncanakan_tidak_dikodekan"),
    (dict(status="dilaporkan_pasien"), "bukan_diagnosis_dokter"),
    (dict(verdict="ditandai", reasons=["dugaan_bukan_diagnosis_pasti"]), "dugaan_tidak_dikodekan"),
    (dict(verdict="ditolak"), "ditolak_validator"),
])
def test_aturan_klinis_tidak_dikodekan(kw, reason):
    r = run(item(**kw), '{"pilihan": 1, "keyakinan": "tinggi"}')
    assert r.state == "kosong" and r.reason == reason and r.suggested_code is None


def test_llm_tidak_boleh_mengarang_kode():
    # LLM menjawab kode dari ingatannya (H40.0, salah untuk hipertensi) alih-alih nomor -> diabaikan
    r = run(item(), '{"kode": "H40.0", "pilihan": "H40.0", "keyakinan": "tinggi"}')
    assert r.state == "kosong" and r.suggested_code is None
    # nomor di luar daftar kandidat
    assert run(item(), '{"pilihan": 99, "keyakinan": "tinggi"}').state == "kosong"
    assert run(item(), '{"pilihan": 0, "keyakinan": "tinggi"}').state == "kosong"
    assert run(item(), "bukan json").state == "kosong"
    assert run(item(), CHOOSE_NONE).state == "kosong"


def test_kode_harus_ada_di_tabel():
    r = run(item(), '{"pilihan": 1, "keyakinan": "tinggi"}', exists=lambda s, c: None)
    assert r.state == "kosong" and r.reason == "kode_tidak_ada_di_tabel"


def test_keyakinan_rendah_kandidat_mirip_dan_butir_ditandai_hanya_saran():
    assert run(item(), '{"pilihan": 1, "keyakinan": "sedang"}').state == "saran"
    assert run(item(), '{"pilihan": 2, "keyakinan": "tinggi"}').state == "saran"          # bukan peringkat 1
    mirip = [dict(CANDS[0], sim=0.90), dict(CANDS[1], sim=0.88), CANDS[2]]
    assert run(item(), '{"pilihan": 1, "keyakinan": "tinggi"}', cands=mirip).reason == "kandidat_mirip"
    r = run(item(verdict="ditandai", reasons=["pembicara_tidak_diketahui_dokter_harus_konfirmasi"]),
            '{"pilihan": 1, "keyakinan": "tinggi"}')
    assert r.state == "saran" and r.reason == "butir_ditandai"


def test_tanpa_kandidat_kosong():
    assert run(item(), '{"pilihan": 1, "keyakinan": "tinggi"}', cands=[]).reason == "tidak_ada_kandidat"


# ------------------------------------------------------------------ parser ClaML (berkas resmi WHO)
needs_xml = pytest.mark.skipif(not XML.exists(), reason="berkas ICD-10 WHO tidak ada")


@needs_xml
def test_claml_resmi_who():
    entries, meta = parse_claml(str(XML))
    d = {e.code: e for e in entries}
    assert meta["version"] == "2019-covid-expanded" and len(entries) > 10000
    assert d["I10"].display == "Essential (primary) hypertension"          # hipertensi esensial = I10
    assert d["E11.9"].display.startswith("Type 2 diabetes mellitus")        # ekspansi modifier WHO
    assert "E11" not in d and "M00.0" not in d and "M00.00" in d            # induk yang diekspansi bukan kode pakai
    assert "H40.0" in d and "hypertension" not in d["H40.0"].display.lower()  # H40.0 bukan hipertensi (jebakan di spesifikasi)
    assert "glaucoma" in d["H40.0"].display.lower()


# ------------------------------------------------------------------ integrasi dengan DB + tabel resmi
@pytest.fixture(scope="session")
def icd(db):
    if not XML.exists():
        pytest.skip("berkas ICD-10 WHO tidak ada")
    from app.db import engine
    from app.terminology.loader import icd10_rows, load_codes
    rows, meta = icd10_rows(str(XML))
    with engine().begin() as c:
        load_codes(c, "ICD10", meta["version"], "https://icdcdn.who.int/icd10/claml/icd102019en.xml.zip", "test", rows)
    return len(rows)


def test_retrieval_dari_tabel_resmi(icd):
    from app.db import engine
    from app.terminology import retrieve
    with engine().begin() as c:
        top = [r["code"] for r in retrieve.retrieve(c, "ICD10", ["essential hypertension"], 8, use_vectors=False)]
        assert "I10" in top[:3]
        top = [r["code"] for r in retrieve.retrieve(c, "ICD10", ["urinary tract infection"], 8, use_vectors=False)]
        assert "N39.0" in top[:3]
        assert retrieve.code_exists(c, "ICD10", "I10")["display"] == "Essential (primary) hypertension"
        assert retrieve.code_exists(c, "ICD10", "ZZZ.99") is None


def _scripted(fakes_):
    def choose(user):
        lines = [ln for ln in user.split("KANDIDAT:\n", 1)[1].splitlines() if "Essential (primary) hypertension" in ln]
        return json.dumps({"pilihan": int(lines[0].split(".")[0]), "keyakinan": "tinggi"}) if lines else CHOOSE_NONE
    fakes_["translate"] = lambda u: json.dumps({"en": "essential hypertension"}) if "hipertensi" in u else json.dumps({"en": u})
    fakes_["choose"] = choose


def test_alur_penuh_dengan_kode(client, tenant, fakes, icd):
    from app.adapters.mock import MockAdapter
    _scripted(fakes)
    fakes["by_channel"] = TWO_CHANNEL
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)
    st = client.get(f"/v1/sessions/{sid}", headers=h).json()
    assert {j["kind"]: j["status"] for j in st["jobs"]}["map_codes"] == "succeeded"
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    items = {i["id"]: i for i in rv["items"]}
    by_teks = {items[c["item_id"]]["teks"]: c for c in rv["codes"]}
    assert set(by_teks) == {"hipertensi", "diabetes"}                       # 'kanker' ditolak -> tidak ada baris kode
    hip = by_teks["hipertensi"]
    assert hip["suggested_code"] == "I10" and hip["suggested_display"] == "Essential (primary) hypertension"
    assert hip["state"] in ("terisi", "saran")
    dm = by_teks["diabetes"]                                                # dugaan dokter: TIDAK dikodekan
    assert dm["state"] == "kosong" and dm["reason"] == "dugaan_tidak_dikodekan" and dm["suggested_code"] is None

    # dokter: kode tak valid ditolak, kode valid diterima, hapus
    cid = hip["id"]
    assert client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": "ZZZ.99"}).status_code == 422
    ok = client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": "I10"})
    assert ok.status_code == 200 and ok.json()["state"] == "dipilih_dokter" and ok.json()["final_code"] == "I10"
    cleared = client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": None}).json()
    assert cleared["state"] == "kosong" and cleared["final_code"] is None
    client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": "I10"})

    # approve -> submit membawa kode final (hanya yang diputuskan/terisi)
    soap = client.get(f"/v1/sessions/{sid}/review", headers=h).json()["soap"]
    saved = client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": [
        {"id": x["id"], "section": x["section"], "text": x["text"]} for x in soap["sentences"]]}).json()
    assert client.post(f"/v1/sessions/{sid}/approve", headers=h,
                       json={"soap_id": saved["id"], "acknowledge_flagged": True}).status_code == 200
    assert client.post(f"/v1/sessions/{sid}/submit", headers=h).status_code == 200
    sent = MockAdapter.submitted[saved["id"]]["soap"]["codes"]
    assert sent == [{"system": "ICD10", "code": "I10", "display": "Essential (primary) hypertension"}]
    actions = [a["action"] for a in client.get(f"/v1/sessions/{sid}/audit", headers=h).json()]
    assert actions.count("code.set") == 3      # kode tak valid ditolak (tidak tercatat)


def test_llm_mengarang_kode_di_pipeline_tidak_masuk(client, tenant, fakes, icd):
    fakes["by_channel"] = TWO_CHANNEL
    fakes["translate"] = lambda u: json.dumps({"en": "hypertension"})
    fakes["choose"] = lambda u: json.dumps({"pilihan": "H40.0", "kode": "H40.0", "keyakinan": "tinggi"})
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    assert rv["codes"] and all(c["suggested_code"] is None and c["final_code"] is None for c in rv["codes"])


def test_pencarian_kode_dokter(client, tenant, icd):
    h = login(client, tenant)
    r = client.get("/v1/terminology/icd10/search", params={"q": "essential hypertension"}, headers=h)
    assert r.status_code == 200 and "I10" in [x["code"] for x in r.json()]
    assert client.get("/v1/terminology/icd10/search", params={"q": "x"}, headers=h).status_code == 422
    assert client.get("/v1/terminology/xyz/search", params={"q": "paracetamol"}, headers=h).status_code == 422


# ------------------------------------------------------------------ Fase 3/4: obat, lab, tindakan (aturan + loader CSV)
def mi(field, status="dinyatakan_dokter", verdict="diterima", **kw):
    return {"teks": kw.pop("teks", "x"), "nama": kw.pop("nama", None), "dosis": kw.pop("dosis", None),
            "evidence": "bukti", "status": status, "verdict": verdict, "reasons": []}, field


def run_item(field, it, choice='{"pilihan": 1, "keyakinan": "tinggi"}'):
    return mapper.map_item(it, field=field, retrieve_fn=lambda s, q, k: [dict(c) for c in CANDS],
                           llm_fn=lambda sy, us: '{"en": "x"}' if sy.startswith("Terjemahkan") else choice,
                           exists_fn=lambda s, c: {"code": c, "display": "d"})


@pytest.mark.parametrize("field,status,state,reason", [
    ("obat", "dinegasi", "kosong", "obat_tidak_dipakai_penanganan_khusus"),
    ("obat", "dinyatakan_dokter", "terisi", None),
    ("obat", "dilaporkan_pasien", "saran", "status_hanya_saran"),
    ("obat", "direncanakan", "saran", "status_hanya_saran"),
    ("tindakan", "direncanakan", "kosong", "direncanakan_tidak_dikodekan_sebagai_tindakan"),
    ("tindakan", "dinegasi", "kosong", "tindakan_tidak_dilakukan"),
    ("tindakan", "dinyatakan_dokter", "terisi", None),
    ("penunjang", "direncanakan", "saran", "status_hanya_saran"),
    ("penunjang", "dinegasi", "kosong", "pemeriksaan_tidak_dilakukan"),
    ("penunjang", "dinyatakan_dokter", "terisi", None),
])
def test_aturan_per_field(field, status, state, reason):
    it, f = mi(field, status)
    r = run_item(f, it)
    assert (r.state, r.reason) == (state, reason)


def test_field_tak_dikenal_tidak_dikodekan():
    it, _ = mi("edukasi")
    assert mapper.eligibility(it, "edukasi")[0] == "field_tidak_dikodekan"


def test_loader_csv_generik(tmp_path):
    from app.terminology.loader import csv_rows
    f = tmp_path / "uji.csv"
    f.write_text("KODE,NAMA,KUAT\nFAKE-KFA-001,paracetamol 500 mg tablet,500 mg\nFAKE-KFA-002,amlodipine 5 mg tablet,5 mg\n"
                 "FAKE-KFA-001,duplikat,\n,tanpa kode,\n", encoding="utf-8")
    rows = csv_rows(str(f), "KODE", "NAMA", ["KUAT"])
    assert [r["code"] for r in rows] == ["FAKE-KFA-001", "FAKE-KFA-002"]       # duplikat & baris tanpa kode dibuang
    assert rows[0]["attrs"] == {"KUAT": "500 mg"} and "paracetamol" in rows[0]["search_text"]


def test_alur_obat_kfa_data_uji(client, tenant, fakes, icd, tmp_path):
    """DATA UJI PALSU (FAKE-KFA-*), bukan KFA asli: memverifikasi jalur kode obat end-to-end."""
    from app.db import engine
    from app.terminology.loader import csv_rows, load_codes
    f = tmp_path / "fake_kfa.csv"
    f.write_text("KODE,NAMA\nFAKE-KFA-001,paracetamol 500 mg tablet\nFAKE-KFA-002,paracetamol 500 mg sirup\n"
                 "FAKE-KFA-003,amlodipine 5 mg tablet\n", encoding="utf-8")
    with engine().begin() as c:
        load_codes(c, "KFA", "UJI", "uji://", "x", csv_rows(str(f), "KODE", "NAMA", []))
    reply = {"items": [{"field": "obat", "teks": "paracetamol 500 mg", "nama": "paracetamol", "dosis": "500 mg",
                        "status": "dinyatakan_dokter", "bukti": "Saya beri paracetamol 500 mg", "segmen": [5]}]}
    fakes["llm_replies"] = [json.dumps(reply)]
    fakes["by_channel"] = TWO_CHANNEL
    fakes["translate"] = lambda u: '{"en": "x"}'
    fakes["choose"] = lambda u: json.dumps({"pilihan": 1, "keyakinan": "tinggi"})
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    kfa = [c for c in rv["codes"] if c["system"] == "KFA"]
    assert len(kfa) == 1 and kfa[0]["suggested_code"].startswith("FAKE-KFA-")
    assert kfa[0]["suggested_code"] in {c["code"] for c in kfa[0]["candidates"]}      # hanya dari kandidat tabel
    # dokter mengganti ke kode lain yang ada di tabel; kode di luar tabel ditolak
    cid = kfa[0]["id"]
    assert client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": "FAKE-KFA-003"}).status_code == 200
    assert client.put(f"/v1/sessions/{sid}/codes/{cid}", headers=h, json={"code": "FAKE-KFA-999"}).status_code == 422


def test_ejaan_inggris_britania_untuk_icd10():
    from app.terminology.retrieve import uk_spelling
    assert uk_spelling("acute diarrhea with edema") == "acute diarrhoea with oedema"
    assert uk_spelling("hypertension") == "hypertension"
