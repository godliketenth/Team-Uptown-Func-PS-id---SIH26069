"""post metadata and credibility flags

Revision ID: 7772bd9fca55
Revises: a9e3145100ff
Create Date: 2026-09-22 21:24:35.559075
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '7772bd9fca55'
down_revision = 'a9e3145100ff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'events',
        sa.Column('flagged_report_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('reports', sa.Column('hashtags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('tracked_hashtags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('mentions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('urls', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('reports', sa.Column('author', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('misinformation_risk', sa.Float(), nullable=True))
    op.add_column('reports', sa.Column('credibility_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f('ix_reports_author'), 'reports', ['author'], unique=False)
    op.create_index(op.f('ix_reports_misinformation_risk'), 'reports', ['misinformation_risk'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reports_misinformation_risk'), table_name='reports')
    op.drop_index(op.f('ix_reports_author'), table_name='reports')
    op.drop_column('reports', 'credibility_flags')
    op.drop_column('reports', 'misinformation_risk')
    op.drop_column('reports', 'author')
    op.drop_column('reports', 'urls')
    op.drop_column('reports', 'mentions')
    op.drop_column('reports', 'tracked_hashtags')
    op.drop_column('reports', 'hashtags')
    op.drop_column('events', 'flagged_report_count')
