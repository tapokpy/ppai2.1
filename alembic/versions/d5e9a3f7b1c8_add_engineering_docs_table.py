"""add engineering_docs table

Revision ID: d5e9a3f7b1c8
Revises: c4b8f2a6d9e1
Create Date: 2026-08-13 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e9a3f7b1c8'
down_revision: Union[str, None] = 'c4b8f2a6d9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'engineering_docs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('doc_type', sa.String(length=10), nullable=False),
        sa.Column('extracted_data', sa.JSON(), nullable=True),
        sa.Column('is_generated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('engineering_docs')
