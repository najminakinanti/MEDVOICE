"""Webhook bertanda tangan, token widget (cakupan satu sesi), pratinjau langsung."""
import hashlib
import hmac
import json

import pytest
from sqlalchemy import text

from tests.conftest import login
from tests.test_flow import SEGMENTS, TWO_CHANNEL, fakes, record_and_finish, start_session  # noqa: F401


def _set_webhook(tenant, url="https://hook.rs.test/cb"):
    from app.db import engine
    with engine().begin() as c:
        c.execute(text("UPDATE clients SET webhook_url=:u WHERE id=:i"), dict(u=url, i=tenant["id"]))


@pytest.fixture()
def hooks(monkeypatch):
    import httpx
    sent = []

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_post(url, content=None, headers=None, timeout=None, **kw):
        sent.append({"url": url, "body": content, "headers": headers})
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    return sent


def test_webhook_bertanda_tangan_dan_tanpa_data_klinis(client, tenant, fakes, hooks):
    from app import security
    _set_webhook(tenant)
    fakes["by_channel"] = TWO_CHANNEL
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)
    assert [x["headers"]["X-MedVoice-Event"] for x in hooks] == ["session.processed"]
    w = hooks[0]
    body = json.loads(w["body"])
    assert body["session_id"] == sid and body["status"] == "review" and body["jobs"]["soap"] == "succeeded"
    blob = w["body"].decode()
    for seg in SEGMENTS:
        assert seg["text"] not in blob
    assert "no_rawat" not in body and "2026/01" not in blob              # tak ada identitas/klinis
    ts = w["headers"]["X-MedVoice-Timestamp"]
    expected = "sha256=" + hmac.new(security.webhook_secret(tenant["id"]).encode(), ts.encode() + b"." + w["body"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(w["headers"]["X-MedVoice-Signature"], expected)
    # approve & submit memicu webhook
    soap = client.get(f"/v1/sessions/{sid}/review", headers=h).json()["soap"]
    saved = client.put(f"/v1/sessions/{sid}/soap", headers=h, json={"sentences": [
        {"id": x["id"], "section": x["section"], "text": x["text"]} for x in soap["sentences"]]}).json()
    client.post(f"/v1/sessions/{sid}/approve", headers=h, json={"soap_id": saved["id"], "acknowledge_flagged": True})
    client.post(f"/v1/sessions/{sid}/submit", headers=h)
    assert [x["headers"]["X-MedVoice-Event"] for x in hooks] == ["session.processed", "session.approved", "session.submitted"]


def test_webhook_gagal_dicatat_dan_tidak_menggagalkan_pipeline(client, tenant, fakes, monkeypatch):
    import httpx
    _set_webhook(tenant)

    def boom(*a, **k):
        raise httpx.ConnectError("x")
    monkeypatch.setattr(httpx, "post", boom)
    fakes["by_channel"] = TWO_CHANNEL
    h = login(client, tenant)
    sid = record_and_finish(client, h, two_channel=True)
    assert client.get(f"/v1/sessions/{sid}", headers=h).json()["status"] == "review"
    actions = [a["action"] for a in client.get(f"/v1/sessions/{sid}/audit", headers=h).json()]
    assert "webhook.failed" in actions


def test_tanpa_webhook_tidak_ada_pengiriman(client, tenant, fakes, hooks):
    fakes["by_channel"] = TWO_CHANNEL
    record_and_finish(client, login(client, tenant), two_channel=True)
    assert hooks == []


def test_token_widget_satu_sesi(client, tenant, fakes):
    hk = {"X-API-Key": tenant["key"]}
    mk = lambda no: client.post("/v1/sessions", headers=hk, json={
        "no_rawat": no, "consent": {"given": True, "recorded_by": "x"}, "doctor": {"simrs_user_id": "dr_a", "display_name": "dr_a"}}).json()["id"]
    s1, s2 = mk("R1"), mk("R2")
    r = client.post(f"/v1/sessions/{s1}/widget-token", headers=hk)
    assert r.status_code == 200 and "token=" in r.json()["ui_path"] and "api" not in r.json()["token"][:4].lower()
    wh = {"Authorization": "Bearer " + r.json()["token"]}
    assert client.get(f"/v1/sessions/{s1}", headers=wh).status_code == 200            # sesi miliknya: boleh
    assert client.get(f"/v1/sessions/{s2}", headers=wh).status_code == 404            # sesi lain: tidak
    assert client.post("/v1/sessions", headers=wh, json={"no_rawat": "R3", "consent": {"given": True, "recorded_by": "x"}}).status_code == 403
    assert client.post(f"/v1/sessions/{s1}/widget-token", headers=wh).status_code == 403   # hanya API key yang boleh menerbitkan
    # token dokter biasa tidak bisa menerbitkan; sesi orang lain tidak bisa dibuatkan token
    assert client.post(f"/v1/sessions/{s1}/widget-token", headers=login(client, tenant)).status_code == 403
    assert client.post("/v1/sessions/00000000-0000-0000-0000-000000000000/widget-token", headers=hk).status_code == 404


def test_widget_alur_penuh_hanya_dengan_token(client, tenant, fakes):
    fakes["by_channel"] = TWO_CHANNEL
    hk = {"X-API-Key": tenant["key"]}
    sid = client.post("/v1/sessions", headers=hk, json={"no_rawat": "RW", "consent": {"given": True, "recorded_by": "x"},
                                                        "doctor": {"simrs_user_id": "dr_a", "display_name": "dr_a"}}).json()["id"]
    tok = client.post(f"/v1/sessions/{sid}/widget-token", headers=hk).json()["token"]
    wh = {"Authorization": "Bearer " + tok}
    files = {"dokter": ("d.webm", b"x", "audio/webm"), "pasien": ("p.webm", b"x", "audio/webm")}
    assert client.post(f"/v1/sessions/{sid}/audio", headers=wh, files=files).status_code == 200
    assert client.post(f"/v1/sessions/{sid}/finish", headers=wh).status_code == 202
    rv = client.get(f"/v1/sessions/{sid}/review", headers=wh)                          # bertindak sebagai dokter sesi ini
    assert rv.status_code == 200 and rv.json()["soap"]["version"] == 1


def test_pratinjau_langsung_tidak_disimpan(client, tenant, fakes):
    import os
    h = login(client, tenant)
    sid = start_session(client, h).json()["id"]
    fakes["segments"] = [{"start_ms": 0, "end_ms": 1000, "text": "Halo dokter"}, {"start_ms": 1000, "end_ms": 2000, "text": "saya pusing"}]
    r = client.post(f"/v1/sessions/{sid}/live", headers=h, files={"chunk": ("c.webm", b"x", "audio/webm")})
    assert r.status_code == 200 and r.json()["text"] == "Halo dokter saya pusing"
    assert [x["text"] for x in r.json()["segments"]] == ["Halo dokter", "saya pusing"]    # per ucapan -> satu gelembung chat
    assert not [d for d in os.listdir(os.environ["AUDIO_DIR"]) if d.startswith("live-")]      # potongan dihapus
    from app.db import engine
    with engine().begin() as c:
        assert c.execute(text("SELECT count(*) FROM transcripts WHERE session_id=:s"), dict(s=sid)).scalar() == 0
    assert client.post(f"/v1/sessions/{sid}/live", headers=h, files={"chunk": ("c.exe", b"x", "x/y")}).status_code == 415
    client.post(f"/v1/sessions/{sid}/finish", headers=h)
    assert client.post(f"/v1/sessions/{sid}/live", headers=h, files={"chunk": ("c.webm", b"x", "audio/webm")}).status_code == 409


def test_csp_widget_dan_statis(client, tenant):
    r = client.get("/ui/")
    assert r.status_code == 200 and "frame-ancestors 'self'" in r.headers["content-security-policy"]
    assert "https://web.rs-a.test" in r.headers["content-security-policy"]                   # origin client boleh embed
    js = client.get("/ui/widget.js")
    assert js.status_code == 200 and "MedVoice" in js.text and "X-API-Key" not in js.text.split("*/", 1)[1]


def test_pratinjau_tahap_akurat_memakai_model_final(client, tenant, fakes, monkeypatch):
    from app import stt_client
    seen = []
    orig = stt_client.transcribe

    def spy(path, prompt, live=False):
        seen.append(live)
        return orig(path, prompt, live)
    monkeypatch.setattr(stt_client, "transcribe", spy)
    h = login(client, tenant)
    sid = start_session(client, h).json()["id"]
    f = {"chunk": ("u.wav", b"x", "audio/wav")}
    assert client.post(f"/v1/sessions/{sid}/live", headers=h, files=f).status_code == 200
    assert client.post(f"/v1/sessions/{sid}/live", headers=h, files=f, data={"accurate": "1"}).status_code == 200
    assert client.post(f"/v1/sessions/{sid}/live", headers=h, files=f, data={"partial": "1"}).status_code == 200
    assert seen == [True, "refine", "partial"]            # cepat = model kecil; accurate = model final; partial = teks sementara


def test_gilir_vram_warmup_dan_bongkar_stt_sebelum_llm(client, tenant, fakes, monkeypatch):
    from app import llm, stt_client
    from app.config import get_settings
    calls = []
    monkeypatch.setattr(get_settings(), "gpu_timeshare", True)
    monkeypatch.setattr(llm, "unload_llm", lambda: calls.append("llm_unload"))
    monkeypatch.setattr(stt_client, "warmup", lambda: calls.append("stt_warmup"))
    monkeypatch.setattr(stt_client, "unload", lambda: calls.append("stt_unload"))
    fakes["by_channel"] = TWO_CHANNEL
    h = login(client, tenant)
    sid = start_session(client, h).json()["id"]
    assert client.post(f"/v1/sessions/{sid}/warmup", headers=h).status_code == 202
    assert calls == ["llm_unload", "stt_warmup"]               # LLM keluar dari VRAM, STT dimuat
    files = {"dokter": ("d.webm", b"x", "audio/webm"), "pasien": ("p.webm", b"x", "audio/webm")}
    client.post(f"/v1/sessions/{sid}/audio", headers=h, files=files)
    assert client.post(f"/v1/sessions/{sid}/finish", headers=h).status_code == 202
    assert calls[-1] == "stt_unload"                           # STT keluar dari VRAM sebelum ekstraksi LLM
    assert client.post(f"/v1/sessions/{sid}/warmup", headers=h).status_code == 409   # sesi sudah tidak merekam


def test_warmup_tanpa_timeshare_tidak_mengganggu_llm(client, tenant, monkeypatch):
    from app import llm, stt_client
    calls = []
    monkeypatch.setattr(llm, "unload_llm", lambda: calls.append("llm_unload"))
    monkeypatch.setattr(stt_client, "warmup", lambda: calls.append("stt_warmup"))
    h = login(client, tenant)
    sid = start_session(client, h).json()["id"]
    assert client.post(f"/v1/sessions/{sid}/warmup", headers=h).status_code == 202
    assert calls == ["stt_warmup"]
