"""Adapter SatuSehat (FHIR). Dipasang bila SATUSEHAT_* dikonfigurasi. BELUM diuji terhadap server sungguhan.

Butuh `refs_resolver(no_rawat, doctor_simrs_id) -> dict|None` dari SIMRS (ID Patient/Encounter/Practitioner/Organization);
tanpa itu pengiriman ditolak (engine tidak mengarang ID)."""
from typing import Callable

import httpx

from ..fhir import FhirError, build_bundle
from .base import SubmitResult


class SatuSehatAdapter:
    name = "satusehat"

    def __init__(self, *, base_url: str, auth_url: str, client_id: str, client_secret: str,
                 refs_resolver: Callable[[str, str], dict | None], timeout: float = 30.0, http=None):
        self.base_url, self.auth_url = base_url.rstrip("/"), auth_url.rstrip("/")
        self.client_id, self.client_secret = client_id, client_secret
        self.refs_resolver, self.timeout = refs_resolver, timeout
        self.http = http or httpx

    def verify_patient_access(self, doctor_simrs_id: str, no_rawat: str) -> bool:
        return self.refs_resolver(no_rawat, doctor_simrs_id) is not None

    def _token(self) -> str:
        r = self.http.post(self.auth_url + "/accesstoken", params={"grant_type": "client_credentials"},
                           data={"client_id": self.client_id, "client_secret": self.client_secret}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["access_token"]

    def submit_soap(self, *, no_rawat, doctor_simrs_id, soap, idempotency_key) -> SubmitResult:
        refs = self.refs_resolver(no_rawat, doctor_simrs_id)
        if not refs:
            return SubmitResult(False, None, "refs_unavailable")
        try:
            bundle = build_bundle(soap={k: soap.get(k, []) for k in "SOAP"}, codes=soap.get("codes", []), refs=refs)
        except FhirError as e:
            return SubmitResult(False, None, str(e)[:80])
        try:
            r = self.http.post(self.base_url, json=bundle, timeout=self.timeout,
                               headers={"Authorization": "Bearer " + self._token(), "X-Idempotency-Key": idempotency_key})
        except httpx.HTTPError as e:
            return SubmitResult(False, None, type(e).__name__)
        return SubmitResult(200 <= r.status_code < 300, r.status_code, None if r.is_success else "satusehat_rejected")
