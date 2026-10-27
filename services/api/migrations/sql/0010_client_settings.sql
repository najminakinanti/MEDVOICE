-- Pengaturan per rumah sakit yang boleh diubah admin RS. NULL = pakai nilai bawaan server (.env).
ALTER TABLE clients ADD COLUMN retention_days integer CHECK (retention_days IS NULL OR retention_days BETWEEN 1 AND 365);
ALTER TABLE clients ADD COLUMN session_minutes integer CHECK (session_minutes IS NULL OR session_minutes BETWEEN 15 AND 1440);
ALTER TABLE clients ADD COLUMN consent_text text CHECK (consent_text IS NULL OR length(consent_text) <= 2000);
-- Hasil uji koneksi SIMRS terakhir (supaya halaman Integrasi menampilkan status tanpa harus menguji ulang).
ALTER TABLE clients ADD COLUMN last_test_at timestamptz;
ALTER TABLE clients ADD COLUMN last_test_ok boolean;
ALTER TABLE clients ADD COLUMN last_test_ms integer;
ALTER TABLE clients ADD COLUMN last_test_detail text;
-- Indeks untuk log audit per RS (urut terbaru) dan filter jenis aksi.
CREATE INDEX audit_log_client_id_idx ON audit_log (client_id, id DESC);
