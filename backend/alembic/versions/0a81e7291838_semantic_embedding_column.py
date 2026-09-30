"""semantic embedding column

Revision ID: 0a81e7291838
Revises: 7772bd9fca55
Create Date: 2026-09-28 02:21:29.844860
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
import pgvector.sqlalchemy


revision = '0a81e7291838'
down_revision = '7772bd9fca55'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector powers the near-duplicate search; the extension must exist
    # before the column type resolves.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column('reports', sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'embedding')
