import json

import httpx
import pytest

from app.adapters.satusehat import SatuSehatAdapter
from app.fhir import FhirError, build_bundle

REFS = {"patient": "Patient/P1", "encounter": "Encounter/E1", "practitioner": "Practitioner/D1", "organization": "Organization/O1"}
SOAP = {"S": ["Keluhan utama: pusing <script>"], "O": [], "A": ["hipertensi"], "P": []}
CODES = [{"system": "ICD10", "code": "I10", "display": "Essential (primary) hypertension"},
         {"system": "KFA", "code": "X", "display": "obat"}]


def test_bundle_struktur():
    b = build_bundle(soap=SOAP, codes=CODES, refs=REFS)
    assert b["resourceType"] == "Bundle" and b["type"] == "transaction"
    types = [e["resource"]["resourceType"] for e in b["entry"]]
    assert types == ["Composition", "Condition"]                 # KFA belum jadi resource sendiri
    cond = b["entry"][1]["resource"]
    assert cond["code"]["coding"][0] == {"system": "http://hl7.org/fhir/sid/icd-10", "code": "I10",
                                         "display": "Essential (primary) hypertension"}
    comp = b["entry"][0]["resource"]
    assert [s["title"] for s in comp["section"]] == ["Subjective", "Objective", "Assessment", "Plan"]
    assert comp["section"][2]["entry"] == [{"reference": b["entry"][1]["fullUrl"]}]
    assert "&lt;script&gt;" in comp["section"][0]["text"]["div"]          # narasi di-escape
    assert "Tidak disebutkan" in comp["section"][1]["text"]["div"]
    assert comp["author"] == [{"reference": "Practitioner/D1"}]
    json.dumps(b)


def test_bundle_tanpa_referensi_ditolak():
    with pytest.raises(FhirError):
        build_bundle(soap=SOAP, codes=CODES, refs={"patient": "Patient/P1"})


def test_adapter_satusehat_dengan_transport_tiruan():
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.method, str(req.url.path)))
        if req.url.path.endswith("/accesstoken"):
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["authorization"] == "Bearer tok"
        assert json.loads(req.content)["resourceType"] == "Bundle"
        return httpx.Response(201, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    a = SatuSehatAdapter(base_url="https://x.test/fhir-r4/v1", auth_url="https://x.test/oauth2/v1", client_id="i",
                         client_secret="s", refs_resolver=lambda n, d: REFS, http=http)
    r = a.submit_soap(no_rawat="R1", doctor_simrs_id="D1", soap={**SOAP, "codes": CODES}, idempotency_key="k")
    assert r.ok and r.http_status == 201 and len(calls) == 2
    nores = SatuSehatAdapter(base_url="https://x.test/b", auth_url="https://x.test/a", client_id="i", client_secret="s",
                             refs_resolver=lambda n, d: None, http=http)
    assert nores.verify_patient_access("D1", "R1") is False
    assert nores.submit_soap(no_rawat="R1", doctor_simrs_id="D1", soap=SOAP, idempotency_key="k").error_code == "refs_unavailable"
