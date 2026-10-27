"""tabel roles, kolom jabatan (title), penjaga cakupan membaca tabel roles"""
from pathlib import Path

from alembic import op

revision = "0009"
down_revision = "0008"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0009_roles_table.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
