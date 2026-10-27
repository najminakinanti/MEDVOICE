"""peran superadmin + client platform"""
from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0008_superadmin.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
