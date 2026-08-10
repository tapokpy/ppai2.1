"""add is_approved to users

Revision ID: c47a1d9e2b3f
Revises: 8a2c1f9d4b6e
Create Date: 2026-08-10 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c47a1d9e2b3f'
down_revision: Union[str, None] = '8a2c1f9d4b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill existing users as approved (grandfathered in) so the new
    # access-control gate doesn't lock out people who already had access.
    # New users created after this migration get is_approved=false by
    # default (see app/bot/middlewares/auth.py) and require /add_user.
    op.add_column('users', sa.Column('is_approved', sa.Boolean(), server_default='true', nullable=False))
    op.alter_column('users', 'is_approved', server_default='false')


def downgrade() -> None:
    op.drop_column('users', 'is_approved')
