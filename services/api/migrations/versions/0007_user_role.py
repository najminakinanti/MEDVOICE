"""peran pengguna (dokter/admin) dan waktu login terakhir"""
from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0007_user_role.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
