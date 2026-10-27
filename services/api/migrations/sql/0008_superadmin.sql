-- Peran superadmin (pengelola platform) di atas admin RS. Superadmin tinggal di "client platform" khusus, bukan di RS,
-- supaya tidak terikat ke satu rumah sakit dan tidak berada di dekat data klinis RS mana pun.
ALTER TABLE clients ADD COLUMN is_platform boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX clients_one_platform_uq ON clients (is_platform) WHERE is_platform;
INSERT INTO clients(name, is_platform) VALUES ('medvoice-platform', true) ON CONFLICT (name) DO NOTHING;

ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('dokter', 'admin', 'superadmin'));

-- Penjaga di database: superadmin HANYA di client platform, dan client platform HANYA berisi superadmin.
CREATE FUNCTION users_role_scope() RETURNS trigger AS $$
DECLARE plat boolean;
BEGIN
  SELECT is_platform INTO plat FROM clients WHERE id = NEW.client_id;
  IF NEW.role = 'superadmin' AND NOT coalesce(plat, false) THEN
    RAISE EXCEPTION 'superadmin hanya boleh di client platform' USING ERRCODE = '23514';
  END IF;
  IF coalesce(plat, false) AND NEW.role <> 'superadmin' THEN
    RAISE EXCEPTION 'client platform hanya berisi superadmin' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
CREATE TRIGGER users_role_scope BEFORE INSERT OR UPDATE OF role, client_id ON users
  FOR EACH ROW EXECUTE FUNCTION users_role_scope();
