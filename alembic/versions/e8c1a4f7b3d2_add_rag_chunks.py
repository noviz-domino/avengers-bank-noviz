"""add rag_chunks with pgvector (ADR 0013)

Revision ID: e8c1a4f7b3d2
Revises: d7b3e5f9a2c1
Create Date: 2026-11-06 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = 'e8c1a4f7b3d2'
down_revision: Union[str, Sequence[str], None] = 'd7b3e5f9a2c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 이미지가 pgvector/pgvector:pg17이어야 한다 (compose.yaml, CI)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('rag_chunks',
        sa.Column('chunk_id', sa.String(length=100), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('tokens', sa.JSON(), nullable=False),
        sa.Column('embedding_model', sa.String(length=50), nullable=False),
        sa.Column('embedding', Vector(768), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('chunk_id'),
    )


def downgrade() -> None:
    op.drop_table('rag_chunks')
    # 확장은 남겨 둔다: 다른 DB 객체가 쓸 수 있고, 다시 올릴 때 IF NOT EXISTS로 넘어간다
