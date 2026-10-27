"""pengaturan per RS (retensi, masa sesi, teks consent), hasil uji koneksi, indeks log audit"""
from pathlib import Path

from alembic import op

revision = "0010"
down_revision = "0009"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0010_client_settings.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
