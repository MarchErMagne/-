"""Rename metadata fields to avoid SQLAlchemy conflicts

Revision ID: 003
Revises: 001
Create Date: 2025-08-21 17:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns(table)}
    return column in cols


def upgrade() -> None:
    bind = op.get_bind()

    # contacts.metadata -> contacts.contact_metadata (если ещё не переименовано)
    if _column_exists(bind, "contacts", "metadata") and not _column_exists(bind, "contacts", "contact_metadata"):
        with op.batch_alter_table("contacts") as batch:
            batch.alter_column("metadata", new_column_name="contact_metadata")

    # Если планировались другие переименования "metadata" в конкретных таблицах — добавьте по аналогии:
    # пример:
    # if _column_exists(bind, "campaigns", "metadata") and not _column_exists(bind, "campaigns", "campaign_metadata"):
    #     with op.batch_alter_table("campaigns") as batch:
    #         batch.alter_column("metadata", new_column_name="campaign_metadata")


def downgrade() -> None:
    bind = op.get_bind()

    # Откатим только если это безопасно и обратная колонка отсутствует
    if _column_exists(bind, "contacts", "contact_metadata") and not _column_exists(bind, "contacts", "metadata"):
        with op.batch_alter_table("contacts") as batch:
            batch.alter_column("contact_metadata", new_column_name="metadata")
