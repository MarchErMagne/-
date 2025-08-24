"""Fix metadata column names

Revision ID: 002
Revises: 001
Create Date: 2025-08-21 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename metadata column in contacts table to contact_metadata
    op.alter_column('contacts', 'metadata', new_column_name='contact_metadata')
    
    # Rename metadata column in analytics table to event_metadata  
    op.alter_column('analytics', 'metadata', new_column_name='event_metadata')


def downgrade() -> None:
    # Revert the column name changes
    op.alter_column('contacts', 'contact_metadata', new_column_name='metadata')
    op.alter_column('analytics', 'event_metadata', new_column_name='metadata')