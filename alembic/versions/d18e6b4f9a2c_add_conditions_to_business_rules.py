"""add conditions to business_rules

Revision ID: d18e6b4f9a2c
Revises: c47a1d9e2b3f
Create Date: 2026-08-10 06:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd18e6b4f9a2c'
down_revision: Union[str, None] = 'c47a1d9e2b3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('business_rules', sa.Column('conditions', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('business_rules', 'conditions')
