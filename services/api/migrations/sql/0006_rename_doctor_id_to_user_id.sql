-- Penyeragaman nama: consult_sessions.doctor_id -> user_id (mengacu ke tabel users). Indeks lookup ikut otomatis.
-- Nama constraint NOT NULL bawaan sengaja tidak disentuh (tidak ada sebagai constraint bernama di PostgreSQL < 18).
ALTER TABLE consult_sessions RENAME COLUMN doctor_id TO user_id;
ALTER TABLE consult_sessions RENAME CONSTRAINT consult_sessions_doctor_id_fkey TO consult_sessions_user_id_fkey;
