"""Rename metadata fields to avoid SQLAlchemy conflicts

Revision ID: 003
Revises: 001
Create Date: 2025-08-21 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Переименовываем metadata в contact_metadata в таблице contacts
    with op.batch_alter_table('contacts') as batch_op:
        batch_op.alter_column('metadata', new_column_name='contact_metadata')
    
    # Переименовываем metadata в event_metadata в таблице analytics
    with op.batch_alter_table('analytics') as batch_op:
        batch_op.alter_column('metadata', new_column_name='event_metadata')


def downgrade() -> None:
    # Возвращаем обратно
    with op.batch_alter_table('contacts') as batch_op:
        batch_op.alter_column('contact_metadata', new_column_name='metadata')
    
    with op.batch_alter_table('analytics') as batch_op:
        batch_op.alter_column('event_metadata', new_column_name='metadata')