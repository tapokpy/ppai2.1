"""add structured_data and rag_debug to messages

Revision ID: e2f7c5a1b8d4
Revises: d18e6b4f9a2c
Create Date: 2026-08-10 06:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f7c5a1b8d4'
down_revision: Union[str, None] = 'd18e6b4f9a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('structured_data', sa.JSON(), nullable=True))
    op.add_column('messages', sa.Column('rag_debug', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'rag_debug')
    op.drop_column('messages', 'structured_data')
