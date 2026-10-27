-- Tabel akun login: doctors -> users. Relasi (FK dari consult_sessions, soap_notes, code_suggestions) ikut otomatis.
-- Kolom consult_sessions.doctor_id diseragamkan menjadi user_id pada migrasi 0006.
ALTER TABLE doctors RENAME TO users;
ALTER TABLE users RENAME CONSTRAINT doctors_pkey TO users_pkey;
ALTER TABLE users RENAME CONSTRAINT doctors_client_id_simrs_user_id_key TO users_client_id_simrs_user_id_key;
ALTER TABLE users RENAME CONSTRAINT doctors_client_id_username_key TO users_client_id_username_key;
ALTER TABLE users RENAME CONSTRAINT doctors_client_id_fkey TO users_client_id_fkey;
ALTER INDEX doctors_email_uq RENAME TO users_email_uq;
ALTER INDEX doctors_nip_uq RENAME TO users_nip_uq;
