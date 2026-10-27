-- Peran pengguna: 'dokter' (default) atau 'admin' (admin RS: kelola pengguna, integrasi SIMRS, pengaturan).
ALTER TABLE users ADD COLUMN role text NOT NULL DEFAULT 'dokter';
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('dokter', 'admin'));
ALTER TABLE users ADD COLUMN last_login_at timestamptz;
-- Akun pertama tiap rumah sakit menjadi admin, supaya tak ada RS tanpa admin setelah migrasi ini.
UPDATE users SET role = 'admin'
 WHERE id IN (SELECT DISTINCT ON (client_id) id FROM users ORDER BY client_id, created_at, username);
