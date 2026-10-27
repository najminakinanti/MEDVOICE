"""tabel doctors -> users"""
from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0005_rename_doctors_to_users.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
