from .base import SubmitResult


_UNIT = "Poli Umum"
# Data contoh (BUKAN pasien nyata) untuk antrean pada lingkungan dev/demo.
_QUEUE = [
    ("2026/10/23/0001", "08:00", "Budi Santoso", "00-12-45-88", "L", 52, "Kontrol hipertensi", "menunggu"),
    ("2026/10/23/0002", "08:20", "Siti Rahmawati", "00-13-02-17", "P", 45, "Sakit kepala 5 hari", "menunggu"),
    ("2026/10/23/0003", "08:40", "Andi Pratama", "00-09-77-31", "L", 29, "Demam & batuk 3 hari", "menunggu"),
    ("2026/10/23/0004", "09:00", "Dewi Lestari", "00-14-20-05", "P", 34, "Nyeri ulu hati", "menunggu"),
    ("2026/10/23/0005", "09:20", "Rudi Hartono", "00-11-63-90", "L", 61, "Kontrol DM tipe 2", "menunggu"),
    ("2026/10/23/0006", "09:40", "Maya Kusuma", "00-15-08-42", "P", 8, "Ruam kulit", "belum_hadir"),
    ("2026/10/23/0007", "10:00", "Hendra Wijaya", "00-10-34-56", "L", 40, "Nyeri pinggang", "menunggu"),
]


class MockAdapter:
    """Adapter uji: selalu mengizinkan dan menerima. Mencatat idempotency key yang sudah dipakai."""
    name = "mock"
    submitted: dict[str, dict] = {}

    def verify_patient_access(self, doctor_simrs_id: str, no_rawat: str) -> bool:
        return True

    def submit_soap(self, *, no_rawat, doctor_simrs_id, soap, idempotency_key) -> SubmitResult:
        self.submitted[idempotency_key] = {"no_rawat": no_rawat, "soap": soap}
        return SubmitResult(ok=True, http_status=200)

    def list_queue(self, doctor_simrs_id: str) -> dict:
        keys = ("no_rawat", "time", "name", "rm", "sex", "age", "complaint", "state")
        return {"unit": _UNIT, "items": [dict(zip(keys, row)) for row in _QUEUE]}

    def patient_info(self, no_rawat: str) -> dict | None:
        for r in _QUEUE:
            if r[0] == no_rawat:
                return {"name": r[2], "rm": r[3], "sex": r[4], "age": r[5], "unit": _UNIT}
        return None
