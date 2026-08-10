"""make telegram_message_id nullable on messages

Revision ID: 8a2c1f9d4b6e
Revises: 5f0e4c22c638
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a2c1f9d4b6e'
down_revision: Union[str, None] = '5f0e4c22c638'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('messages', 'telegram_message_id', existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    op.alter_column('messages', 'telegram_message_id', existing_type=sa.BigInteger(), nullable=False)
