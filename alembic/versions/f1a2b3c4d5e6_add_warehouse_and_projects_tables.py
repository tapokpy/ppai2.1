"""add warehouse and projects tables

Revision ID: f1a2b3c4d5e6
Revises: d5e9a3f7b1c8
Create Date: 2026-08-14 01:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd5e9a3f7b1c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('customer', sa.String(length=255), nullable=True),
        sa.Column('bom_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'project_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='config'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column('engineering_docs', sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True))

    op.create_table(
        'warehouses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'racks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'shelves',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('rack_id', sa.Integer(), sa.ForeignKey('racks.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'cells',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('shelf_id', sa.Integer(), sa.ForeignKey('shelves.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'stock_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cell_id', sa.Integer(), sa.ForeignKey('cells.id'), nullable=False),
        sa.Column('item_name', sa.String(length=255), nullable=False),
        sa.Column('item_type', sa.String(length=30), nullable=False, server_default='other'),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(length=20), nullable=False, server_default='шт'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('stock_items')
    op.drop_table('cells')
    op.drop_table('shelves')
    op.drop_table('racks')
    op.drop_table('warehouses')
    op.drop_column('engineering_docs', 'project_id')
    op.drop_table('project_files')
    op.drop_table('projects')
