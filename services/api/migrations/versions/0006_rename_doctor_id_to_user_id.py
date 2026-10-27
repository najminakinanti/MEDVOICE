"""kolom consult_sessions.doctor_id -> user_id"""
from pathlib import Path

from alembic import op

revision = "0006"
down_revision = "0005"

SQL = Path(__file__).resolve().parent.parent / "sql" / "0006_rename_doctor_id_to_user_id.sql"


def upgrade() -> None:
    op.execute(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError
