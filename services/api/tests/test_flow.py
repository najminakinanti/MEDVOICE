"""Tes integrasi alur Fase 1 dengan DB nyata; STT dan LLM disimulasikan (bukan model sungguhan)."""
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import login

SEGMENTS = [
    {"start_ms": 0, "end_ms": 3000, "text": "Selamat pagi, ada keluhan apa?"},
    {"start_ms": 3000, "end_ms": 7000, "text": "Saya demam tiga hari, Dok."},
    {"start_ms": 7000, "end_ms": 10000, "text": "Ada alergi obat?"},
    {"start_ms": 10000, "end_ms": 12000, "text": "Tidak ada alergi."},
    {"start_ms": 12000, "end_ms": 16000, "text": "Tekanan darah Bapak 150/90 mmHg. Diagnosisnya hipertensi."},
    {"start_ms": 16000, "end_ms": 20000, "text": "Saya curiga ada diabetes juga. Saya beri paracetamol 500 mg."},
]

GOOD_LLM = {"items": [
    {"field": "keluhan_utama", "teks": "demam 3 hari", "status": "dilaporkan_pasien", "bukti": "Saya demam tiga hari", "segmen": [1]},
    {"field": "alergi", "teks": "alergi obat", "status": "dinegasi", "bukti": "Tidak ada alergi", "segmen": [3]},
    {"field": "tanda_vital", "teks": "TD 150/90 mmHg", "status": "dinyatakan_dokter", "bukti": "Tekanan darah Bapak 150/90 mmHg", "segmen": [4]},
    {"field": "diagnosis", "teks": "hipertensi", "status": "dinyatakan_dokter", "bukti": "Diagnosisnya hipertensi", "segmen": [4]},
    {"field": "diagnosis", "teks": "diabetes", "status": "dinyatakan_dokter", "bukti": "Saya curiga ada diabetes juga", "segmen": [5]},
    {"field": "obat", "teks": "paracetamol", "nama": "paracetamol", "dosis": "1000 mg", "status": "dinyatakan_dokter",
     "bukti": "Saya beri paracetamol 500 mg", "segmen": [5]},          # dosis dikarang -> harus ditolak
    {"field": "diagnosis", "teks": "kanker", "status": "dinyatakan_dokter", "bukti": "kanker paru", "segmen": [5]},  # bukti palsu
]}


@pytest.fixture()
def fakes(monkeypatch):
    from app import llm, stt_client
    state = {"translate": lambda u: "{}", "choose": lambda u: '{"pilihan": null, "keyakinan": "rendah"}', "by_channel": None, "llm_replies": [json.dumps(GOOD_LLM)], "segments": SEGMENTS, "llm_calls": 0}

    def fake_stt(path, prompt, live=False):
        assert Path(path).exists()
        by = state.get("by_channel")
        segs = by[Path(path).stem] if by else state["segments"]
        return {"model": "fake-stt", "language": "id", "segments": list(segs)}

    def fake_llm(system, user, *, json_mode=True, model=None):
        if system.startswith("Terjemahkan"):
            return state["translate"](user)
        if system.startswith("Anda membantu pengodean"):
            return state["choose"](user)
        i = state["llm_calls"]
        state["llm_calls"] += 1
        replies = state["llm_replies"]
        return replies[min(i, len(replies) - 1)]

    monkeypatch.setattr(stt_client, "transcribe", fake_stt)
    monkeypatch.setattr(llm, "call_llm", fake_llm)
    return state


def start_session(client, h, no_rawat="2026/01/01/000001", consent=True):
    return client.post("/v1/sessions", headers=h, json={
        "no_rawat": no_rawat, "consent": {"given": consent, "recorded_by": "perawat uji"}})


TWO_CHANNEL = {"dokter": [SEGMENTS[i] for i in (0, 2, 4, 5)], "pasien": [SEGMENTS[i] for i in (1, 3)]}


def record_and_finish(client, h, two_channel=False):
    sid = start_session(client, h).json()["id"]
    files = ({"dokter": ("d.webm", b"x", "audio/webm"), "pasien": ("p.webm", b"x", "audio/webm")} if two_channel
             else {"mixed": ("a.webm", b"fake-audio", "audio/webm")})
    up = client.post(f"/v1/sessions/{sid}/audio", headers=h, files=files)
    assert up.status_code == 200, up.text
    fin = client.post(f"/v1/sessions/{sid}/finish", headers=h)
    assert fin.status_code == 202
    return sid


def test_satu_kanal_diagnosis_harus_dikonfirmasi_dokter(client, tenant, fakes):
    h = login(client, tenant)
    sid = record_and_finish(client, h)                      # kanal 'mixed' -> pembicara tak diketahui
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    hip = next(i for i in rv["items"] if i["teks"] == "hipertensi")
    assert hip["verdict"] == "ditandai"
    assert "pembicara_tidak_diketahui_dokter_harus_konfirmasi" in hip["reasons"]


def test_full_flow_review_approve_submit(client, tenant, fakes):
    fakes["by_channel"] = TWO_CHANNEL
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)

    st = client.get(f"/v1/sessions/{sid}", headers=h).json()
    assert st["status"] == "review", st
    jobs = {j["kind"]: j for j in st["jobs"]}
    assert {k: jobs[k]["status"] for k in ("stt", "extract", "validate", "soap")} == {k: "succeeded" for k in ("stt", "extract", "validate", "soap")}
    assert jobs["map_codes"]["status"] in ("succeeded", "failed")      # gagal lunak bila tabel belum dimuat; tak menghalangi SOAP
    assert not (Path(os.environ["AUDIO_DIR"]) / sid).exists()          # audio dihapus

    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    verdicts = {(i["field"], i["teks"]): i["verdict"] for i in rv["items"]}
    assert verdicts[("keluhan_utama", "demam 3 hari")] == "diterima"
    assert verdicts[("alergi", "alergi obat")] == "diterima"
    assert verdicts[("diagnosis", "hipertensi")] == "diterima"
    assert verdicts[("diagnosis", "diabetes")] == "ditandai"          # dugaan
    assert verdicts[("obat", "paracetamol")] == "ditolak"             # dosis karangan
    assert verdicts[("diagnosis", "kanker")] == "ditolak"             # bukti palsu
    # waktu bukti dari kode, bukan LLM
    hip = next(i for i in rv["items"] if i["teks"] == "hipertensi")
    assert (hip["start_ms"], hip["end_ms"]) == (12000, 16000)

    text_all = " ".join(s["text"] for s in rv["soap"]["sentences"])
    assert "kanker" not in text_all and "1000" not in text_all
    a = [s for s in rv["soap"]["sentences"] if s["section"] == "A"]
    assert a[0]["text"] == "Diagnosis: hipertensi" or a[0]["text"] == "hipertensi"
    assert any(s["is_ai_suspicion"] and s["text"].startswith("[Dugaan") for s in a)
    assert all(s["evidence_item_ids"] for s in rv["soap"]["sentences"] if s["text"] != "Tidak disebutkan")
    assert rv["soap"]["source"] == "ai" and rv["soap"]["version"] == 1
    # butir terlewat: paracetamol 500 mg ditolak -> muncul di terlewat
    assert any(m["kind"] == "obat" and m["mention"] == "paracetamol" for m in rv["missed"])

    # approve versi AI murni ditolak
    r = client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": rv["soap"]["id"]})
    assert r.status_code == 409 and r.json()["detail"] == "doctor_version_required"
    # submit sebelum approve ditolak
    assert client.post(f"/v1/sessions/{sid}/submit", headers=h).status_code == 409

    # dokter menyimpan (edit satu kalimat + hapus satu + tambah satu)
    sents = rv["soap"]["sentences"]
    payload = []
    for s in sents:
        if s["section"] == "O" and s["text"] != "Tidak disebutkan":
            payload.append({"id": s["id"], "section": "O", "text": s["text"] + " (diperiksa dokter)"})
        elif s["is_ai_suspicion"]:
            continue                                                  # dokter menghapus dugaan
        else:
            payload.append({"id": s["id"], "section": s["section"], "text": s["text"]})
    payload.append({"section": "P", "text": "Kontrol 1 minggu"})
    r = client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": payload})
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["source"] == "dokter"
    edited = [s for s in v2["sentences"] if s["origin"] == "dokter_edit"]
    assert edited and edited[0]["ai_text"] and "(diperiksa dokter)" in edited[0]["text"]
    assert any(s["origin"] == "dokter_baru" for s in v2["sentences"])

    # approve: ada kalimat bertanda -> wajib acknowledge
    flagged = any(s["flagged"] for s in v2["sentences"])
    if flagged:
        r = client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": v2["id"]})
        assert r.status_code == 409 and r.json()["detail"] == "flagged_not_acknowledged"
    r = client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": v2["id"], "acknowledge_flagged": True})
    assert r.status_code == 200, r.text
    # tak bisa edit setelah approve
    assert client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": payload}).status_code == 409

    r = client.post(f"/v1/sessions/{sid}/submit", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    r2 = client.post(f"/v1/sessions/{sid}/submit", headers=h)
    assert r2.json().get("idempotent") is True

    from app.adapters.mock import MockAdapter
    sent = MockAdapter.submitted[v2["id"]]
    assert "Kontrol 1 minggu" in sent["soap"]["P"]

    actions = [a["action"] for a in client.get(f"/v1/sessions/{sid}/audit", headers=h).json()]
    for need in ("session.create", "audio.upload", "session.finish", "audio.deleted", "soap.ai_generated",
                 "review.view", "soap.edit", "soap.approve", "simrs.submit"):
        assert need in actions, need


def test_soap_kosong_tidak_bisa_approve(client, tenant, fakes):
    fakes["segments"] = []
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    r = client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": []})
    assert r.status_code == 200
    r2 = client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": r.json()["id"]})
    assert r2.status_code == 409 and r2.json()["detail"] == "soap_kosong"


def test_consent_wajib_dan_auth(client, tenant):
    h = login(client, tenant)
    assert start_session(client, h, consent=False).status_code == 422
    assert client.post("/v1/sessions", json={}).status_code == 401
    assert client.get("/v1/sessions/xxx", headers=h).status_code == 404
    assert client.post("/v1/auth/login", json={"client": tenant["name"], "username": "dr_a", "password": "salah-salah"}).status_code == 401


def test_dokter_hanya_melihat_pasiennya_dan_tenant_terpisah(client, tenant, fakes):
    ha, hb = login(client, tenant, "dr_a"), login(client, tenant, "dr_b")
    sid = record_and_finish(client, ha)
    assert client.get(f"/v1/sessions/{sid}", headers=hb).status_code == 404
    assert client.get(f"/v1/sessions/{sid}/review", headers=hb).status_code == 404
    assert client.put(f"/v1/sessions/{sid}/soap", headers=hb, json={"sentences": []}).status_code == 404


def test_api_key_tidak_bisa_review_tapi_bisa_buat_sesi(client, tenant):
    hk = {"X-API-Key": tenant["key"]}
    r = client.post("/v1/sessions", headers=hk, json={
        "no_rawat": "R1", "consent": {"given": True, "recorded_by": "x"},
        "doctor": {"simrs_user_id": "D99", "display_name": "dr. Baru"}})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.get(f"/v1/sessions/{sid}/review", headers=hk).status_code == 403
    assert client.get(f"/v1/sessions/{sid}", headers=hk).status_code == 200
    assert client.get(f"/v1/sessions/{sid}", headers={"X-API-Key": "mvk_salah"}).status_code == 401


def test_cors_per_client(client, tenant):
    hk = {"X-API-Key": tenant["key"]}
    ok = client.get("/v1/health", headers={"Origin": "https://web.rs-a.test"})
    assert ok.status_code == 200
    bad = client.post("/v1/sessions", headers={**hk, "Origin": "https://evil.test"},
                      json={"no_rawat": "R", "consent": {"given": True, "recorded_by": "x"},
                            "doctor": {"simrs_user_id": "D1", "display_name": "x"}})
    assert bad.status_code == 403 and bad.json()["detail"] == "origin_not_allowed"
    good = client.post("/v1/sessions", headers={**hk, "Origin": "https://web.rs-a.test"},
                       json={"no_rawat": "R", "consent": {"given": True, "recorded_by": "x"},
                             "doctor": {"simrs_user_id": "D1", "display_name": "x"}})
    assert good.status_code == 201
    assert good.headers.get("access-control-allow-origin") == "https://web.rs-a.test"


def test_rate_limit_dan_kuota(client, tenant):
    with __import__("app.db", fromlist=["engine"]).engine().begin() as c:
        c.execute(text("UPDATE clients SET rate_limit_per_min=3, monthly_quota=1 WHERE id=:i"), dict(i=tenant["id"]))
    hk = {"X-API-Key": tenant["key"]}
    body = {"no_rawat": "R", "consent": {"given": True, "recorded_by": "x"}, "doctor": {"simrs_user_id": "D1", "display_name": "x"}}
    assert client.post("/v1/sessions", headers=hk, json=body).status_code == 201
    r = client.post("/v1/sessions", headers=hk, json=body)
    assert r.status_code == 429 and r.json()["detail"] == "monthly_quota_exceeded"
    client.get("/v1/jobs/" + "0" * 8 + "-0000-0000-0000-000000000000", headers=hk)
    assert client.get("/v1/jobs/" + "0" * 8 + "-0000-0000-0000-000000000000", headers=hk).status_code == 429


def test_stt_kosong_jalur_manual(client, tenant, fakes):
    fakes["segments"] = []
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    assert rv["session"]["status"] == "failed" and "stt_kosong_isi_manual" in rv["notices"]
    assert rv["soap"] is None
    # dokter mengisi manual lalu approve
    r = client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": [{"section": "S", "text": "Isi manual dokter"}]})
    assert r.status_code == 200
    secs = {s["section"]: s["text"] for s in r.json()["sentences"]}
    assert secs["S"] == "Isi manual dokter" and secs["O"] == "Tidak disebutkan"
    assert client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": r.json()["id"]}).status_code == 200


def test_json_llm_rusak_dicoba_ulang_sekali_lalu_manual(client, tenant, fakes):
    fakes["llm_replies"] = ["bukan json", json.dumps(GOOD_LLM)]
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    assert client.get(f"/v1/sessions/{sid}", headers=h).json()["status"] == "review"
    assert fakes["llm_calls"] == 2

    fakes.update(llm_calls=0, llm_replies=["rusak", "{juga rusak"])
    sid2 = record_and_finish(client, h)
    rv = client.get(f"/v1/sessions/{sid2}/review", headers=h).json()
    assert fakes["llm_calls"] == 2
    assert "json_llm_rusak_isi_manual" in rv["notices"] and rv["soap"] is None


def test_kualitas_rendah_peringatan(client, tenant, fakes):
    bad = {"items": [{"field": "diagnosis", "teks": f"x{i}", "status": "dinyatakan_dokter",
                      "bukti": f"karangan nomor {i}", "segmen": [0]} for i in range(4)]}
    fakes["llm_replies"] = [json.dumps(bad)]
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    assert "kualitas_draft_rendah" in client.get(f"/v1/sessions/{sid}/review", headers=h).json()["notices"]


def test_llm_mati_pipeline_gagal_tanpa_bocor_isi(client, tenant, fakes, monkeypatch):
    from app import llm
    def boom(*a, **k):
        raise llm.LLMError("ConnectError")
    monkeypatch.setattr(llm, "call_llm", boom)
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    st = client.get(f"/v1/sessions/{sid}", headers=h).json()
    assert st["status"] == "failed"
    jobs = {j["kind"]: j for j in st["jobs"]}
    assert jobs["extract"]["error_code"] == "LLMError" and jobs["soap"]["error_code"] == "skipped_prior_failure"


def test_purge_transkrip_kedaluwarsa(client, tenant, fakes):
    from app.db import engine
    from app.soap_pipeline import purge_expired
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    with engine().begin() as c:
        c.execute(text("UPDATE transcripts SET purge_after = now() - interval '1 day' WHERE session_id=:s"), dict(s=sid))
    assert purge_expired()["transcripts_purged"] >= 1
    rv = client.get(f"/v1/sessions/{sid}/review", headers=h).json()
    assert rv["transcript"]["segments"] == [] and "transkrip_sudah_dihapus_sesuai_retensi" in rv["notices"]
    assert rv["soap"] is not None                                # SOAP tetap ada


def test_audit_log_tidak_memuat_isi_transkrip(client, tenant, fakes):
    from app.db import engine
    h = login(client, tenant)
    sid = record_and_finish(client, h)
    client.get(f"/v1/sessions/{sid}/review", headers=h)
    with engine().begin() as c:
        blob = c.execute(text("SELECT string_agg(coalesce(before::text,'')||coalesce(after::text,'')||action, ' ') "
                              "FROM audit_log WHERE session_id=:s"), dict(s=sid)).scalar()
    for seg in SEGMENTS:
        assert seg["text"] not in blob
