-- Login tanpa memilih rumah sakit: dokter dikenali lewat email atau NIP (unik di seluruh sistem), RS diambil dari client_id dokter.
ALTER TABLE doctors ADD COLUMN email text;
ALTER TABLE doctors ADD COLUMN nip text;
CREATE UNIQUE INDEX doctors_email_uq ON doctors (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX doctors_nip_uq ON doctors (nip) WHERE nip IS NOT NULL;
