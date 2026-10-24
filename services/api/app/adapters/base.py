"""Antarmuka adapter SIMRS. Engine TIDAK menulis ke SIMRS langsung; semua lewat adapter ini.
Satu adapter per SIMRS; dipilih per client lewat kolom clients.simrs_adapter."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class SubmitResult:
    ok: bool
    http_status: int | None = None
    error_code: str | None = None


class SimrsAdapter(Protocol):
    name: str

    def verify_patient_access(self, doctor_simrs_id: str, no_rawat: str) -> bool:
        """Apakah dokter ini berhak atas pasien/no_rawat ini."""

    def submit_soap(self, *, no_rawat: str, doctor_simrs_id: str, soap: dict,
                    idempotency_key: str) -> SubmitResult:
        """Simpan SOAP final yang sudah di-approve. soap = {"S": [...], "O": [...], "A": [...], "P": [...]}."""


# Opsional (UI antrean/riwayat). Adapter yang tidak mengimplementasikannya tetap valid: UI jatuh ke "Sesi Manual".
#   list_queue(doctor_simrs_id) -> {"unit": str, "items": [{"no_rawat","time","name","rm","sex","age","complaint","state"}]}
#       state: "menunggu" | "belum_hadir"
#   patient_info(no_rawat) -> {"name","rm","sex","age","unit"} | None
