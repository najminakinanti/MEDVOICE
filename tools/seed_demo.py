"""Isi data CONTOH (fiktif) untuk pengembangan: beberapa rumah sakit dan beberapa akun untuk tiap peran.
HANYA untuk dev/data simulasi. Nama, email (.example), dan NIP di bawah ini rekaan, bukan orang sungguhan.
Kata sandi di bawah ini terkenal (ada di repo): JANGAN dipakai di server sungguhan.
Aman dijalankan berulang: akun yang sudah ada dilewati, kecuali kata sandinya disetel ulang ke nilai di bawah.

  cd services/api  &&  (muat .env)  &&  ..\\..\\.venv\\Scripts\\python ..\\..\\tools\\seed_demo.py
Akun `dr_budi` (milik Anda sendiri) tidak disentuh."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "api"))

from sqlalchemy import text  # noqa: E402

from app import security  # noqa: E402
from app.config import get_settings, require_secrets  # noqa: E402
from app.db import engine  # noqa: E402

ORIGIN = os.environ.get("SEED_ORIGIN", "http://localhost:8000")
PLATFORM = "medvoice-platform"                      # client khusus superadmin (dibuat migrasi 0008)
HOSPITALS = ["rs-saya", "rs-medika-jakarta", "rs-harapan-bandung", "rs-sehat-surabaya"]

PASSWORD = {"superadmin": "SuperAdmin-2026", "admin": "AdminRS-2026", "dokter": "Dokter-2026"}

# (client, username, simrs_user_id, nama tampil, email, NIP 18 digit atau None, peran, jabatan)
USERS = [
    # --- superadmin (pengelola platform)
    (PLATFORM, "superadmin", "SA-01", "Super Admin MedVoice", "superadmin@medvoice.example", None, "superadmin", "Pengelola Platform"),
    (PLATFORM, "nadia.pratiwi", "SA-02", "Nadia Pratiwi", "nadia.pratiwi@medvoice.example", "199002142015022001", "superadmin", "Operasional Platform"),
    (PLATFORM, "rizky.hakim", "SA-03", "Rizky Hakim", "rizky.hakim@medvoice.example", "198905302014031003", "superadmin", "Dukungan Teknis"),
    # --- admin RS
    ("rs-saya", "lina.marlina", "ADM-SAYA-01", "Lina Marlina", "lina.marlina@rs-saya.example", "198711202012012004", "admin", "Admin Sistem"),
    ("rs-medika-jakarta", "anisa.putri", "DR-JKT-01", "dr. Anisa Putri", "anisa.putri@rsmedika.example", "198812052014032001", "admin", "Dokter Umum"),
    ("rs-medika-jakarta", "dimas.prakoso", "ADM-JKT-01", "Dimas Prakoso", "dimas.prakoso@rsmedika.example", "198402172010011006", "admin", "Admin RS"),
    ("rs-harapan-bandung", "dewi.anggraini", "DR-BDG-01", "dr. Dewi Anggraini, Sp.OG", "dewi.anggraini@rsharapan.example", "198606242012022004", "admin", "Sp.OG"),
    ("rs-sehat-surabaya", "fajar.nugroho", "DR-SBY-01", "dr. Fajar Nugroho, Sp.JP", "fajar.nugroho@rssehat.example", "198204112009011007", "admin", "Sp.JP"),
    # --- dokter
    ("rs-saya", "dr_citra", "DR-SAYA-02", "dr. Citra Lestari, Sp.PD", "citra.lestari@rs-saya.example", "198503122010012003", "dokter", "Sp.PD"),
    ("rs-medika-jakarta", "bagas.pratama", "DR-JKT-02", "dr. Bagas Pratama, Sp.A", "bagas.pratama@rsmedika.example", "198109172008011005", "dokter", "Sp.A"),
    ("rs-medika-jakarta", "bambang.rahardjo", "DR-JKT-03", "dr. Bambang Rahardjo, Sp.PD", "bambang.rahardjo@rsmedika.example", "197905082006041002", "dokter", "Sp.PD"),
    ("rs-medika-jakarta", "eka.saputra", "DR-JKT-04", "dr. Eka Saputra", "eka.saputra@rsmedika.example", "199103252018031001", "dokter", "Dokter Umum"),
    ("rs-harapan-bandung", "eko.wijaya", "DR-BDG-02", "dr. Eko Wijaya", "eko.wijaya@rsharapan.example", "199001302016031002", "dokter", "Dokter Umum"),
    ("rs-harapan-bandung", "hana.wulandari", "DR-BDG-03", "dr. Hana Wulandari, Sp.A", "hana.wulandari@rsharapan.example", "198807142015032005", "dokter", "Sp.A"),
    ("rs-sehat-surabaya", "gita.permata", "DR-SBY-02", "dr. Gita Permata", "gita.permata@rssehat.example", "199308082019032006", "dokter", "Dokter Umum"),
    ("rs-sehat-surabaya", "ilham.syahputra", "DR-SBY-03", "dr. Ilham Syahputra", "ilham.syahputra@rssehat.example", "199206192019031004", "dokter", "Dokter Umum"),
]


def main() -> int:
    require_secrets(get_settings())
    hashes = {role: security.hash_password(pw) for role, pw in PASSWORD.items()}
    made_c = made_u = reset = 0
    with engine().begin() as c:
        ids = {}
        for name in HOSPITALS:
            cid = c.execute(text("SELECT id FROM clients WHERE name=:n"), dict(n=name)).scalar()
            if not cid:
                cid = c.execute(text("INSERT INTO clients(name, allowed_origins) VALUES (:n, ARRAY[:o]) RETURNING id"), dict(n=name, o=ORIGIN)).scalar()
                made_c += 1
            ids[name] = cid
        ids[PLATFORM] = c.execute(text("SELECT id FROM clients WHERE is_platform")).scalar()
        if not ids[PLATFORM]:
            sys.exit("client platform tidak ada: jalankan migrasi (alembic upgrade head)")
        for client, uname, simrs, nama, email, nip, role, title in USERS:
            before = c.execute(text("SELECT id FROM users WHERE client_id=:c AND username=:u"), dict(c=ids[client], u=uname)).scalar()
            c.execute(text(
                "INSERT INTO users(client_id, simrs_user_id, username, password_hash, display_name, email, nip, role, title) "
                "VALUES (:c,:s,:u,:p,:n,:e,:i,:r,:t) "
                "ON CONFLICT (client_id, username) DO UPDATE SET password_hash=EXCLUDED.password_hash, "
                "title=COALESCE(users.title, EXCLUDED.title), active=true"),
                dict(c=ids[client], s=simrs, u=uname, p=hashes[role], n=nama, e=email, i=nip, r=role, t=title))
            made_u, reset = (made_u + 1, reset) if not before else (made_u, reset + 1)
    print(f"rumah sakit baru: {made_c} | akun baru: {made_u} | akun lama disetel ulang kata sandinya: {reset}")
    print("\nPERAN        LOGIN (email / NIP)                          KATA SANDI        RUMAH SAKIT")
    for client, uname, simrs, nama, email, nip, role, title in USERS:
        print(f"{role:<12} {email:<44} {PASSWORD[role]:<17} {'(platform)' if client == PLATFORM else client}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
