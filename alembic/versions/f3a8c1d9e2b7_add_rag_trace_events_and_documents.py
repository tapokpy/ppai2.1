"""add rag_trace_events and documents tables, timing/rag_trace_id on messages

Revision ID: f3a8c1d9e2b7
Revises: e2f7c5a1b8d4
Create Date: 2026-08-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d9e2b7'
down_revision: Union[str, None] = 'e2f7c5a1b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('timing', sa.JSON(), nullable=True))
    op.add_column('messages', sa.Column('rag_trace_id', sa.String(length=36), nullable=True))
    op.create_index('ix_messages_rag_trace_id', 'messages', ['rag_trace_id'])

    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('char_count', sa.Integer(), nullable=True),
        sa.Column('ocr_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('embedding_model', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ingested'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_documents_source', 'documents', ['source'])
    op.create_index('ix_documents_filename', 'documents', ['filename'])

    op.create_table(
        'rag_trace_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trace_id', sa.String(length=36), nullable=False),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('event_name', sa.String(length=40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_rag_trace_events_trace_id', 'rag_trace_events', ['trace_id'])
    op.create_index('ix_rag_trace_events_message_id', 'rag_trace_events', ['message_id'])


def downgrade() -> None:
    op.drop_index('ix_rag_trace_events_message_id', table_name='rag_trace_events')
    op.drop_index('ix_rag_trace_events_trace_id', table_name='rag_trace_events')
    op.drop_table('rag_trace_events')

    op.drop_index('ix_documents_filename', table_name='documents')
    op.drop_index('ix_documents_source', table_name='documents')
    op.drop_table('documents')

    op.drop_index('ix_messages_rag_trace_id', table_name='messages')
    op.drop_column('messages', 'rag_trace_id')
    op.drop_column('messages', 'timing')
