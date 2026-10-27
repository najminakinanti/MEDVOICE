-- Tabel role: sumber tunggal daftar peran akses. Hak akses sebenarnya tetap ditegakkan kode (deps.py);
-- tabel ini menyimpan nama, cakupan (hospital = di dalam satu RS, platform = lintas RS), urutan, dan penjelasan.
CREATE TABLE roles (
    code        text PRIMARY KEY,
    label       text NOT NULL,
    scope       text NOT NULL CHECK (scope IN ('hospital', 'platform')),
    rank        integer NOT NULL UNIQUE,            -- makin besar makin tinggi; dipakai untuk "minimal satu pengelola aktif"
    description text NOT NULL DEFAULT ''
);
INSERT INTO roles(code, label, scope, rank, description) VALUES
 ('dokter',     'Dokter',     'hospital', 1, 'Alur klinis: antrean, rekam konsultasi, review dan setujui SOAP, riwayat sesi sendiri, profil sendiri.'),
 ('admin',      'Admin RS',   'hospital', 2, 'Semua yang bisa dilakukan dokter, ditambah mengelola pengguna, integrasi SIMRS, dan pengaturan rumah sakitnya sendiri.'),
 ('superadmin', 'Superadmin', 'platform', 3, 'Pengelola platform: membuat dan mengatur rumah sakit serta penggunanya. Tidak punya akses data klinis.');

-- Kolom peran menjadi kunci asing ke tabel role (menggantikan CHECK berisi daftar tetap).
ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_fkey FOREIGN KEY (role) REFERENCES roles(code);

-- Jabatan: teks bebas yang tampil di kolom PERAN pada desain (mis. Dokter Umum, Sp.PD, Perawat); bukan hak akses.
ALTER TABLE users ADD COLUMN title text;

-- Penjaga cakupan kini membaca tabel role: peran ber-scope 'platform' hanya di client platform, 'hospital' hanya di RS.
CREATE OR REPLACE FUNCTION users_role_scope() RETURNS trigger AS $$
DECLARE plat boolean; rscope text;
BEGIN
  SELECT is_platform INTO plat FROM clients WHERE id = NEW.client_id;
  SELECT scope INTO rscope FROM roles WHERE code = NEW.role;
  IF rscope IS DISTINCT FROM (CASE WHEN coalesce(plat, false) THEN 'platform' ELSE 'hospital' END) THEN
    RAISE EXCEPTION 'peran % tidak boleh dipakai di client ini', NEW.role USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
