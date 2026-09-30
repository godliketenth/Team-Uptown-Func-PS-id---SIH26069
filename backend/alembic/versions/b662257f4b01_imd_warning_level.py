"""imd warning level

Revision ID: b662257f4b01
Revises: 0a81e7291838
Create Date: 2026-09-29 07:11:18.714452
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = 'b662257f4b01'
down_revision = '0a81e7291838'
branch_labels = None
depends_on = None


def upgrade() -> None:
    warning_level = postgresql.ENUM(
        'GREEN', 'YELLOW', 'ORANGE', 'RED', name='warning_level'
    )
    warning_level.create(op.get_bind(), checkfirst=True)
    op.add_column('events', sa.Column('warning_level', postgresql.ENUM('GREEN', 'YELLOW', 'ORANGE', 'RED', name='warning_level', create_type=False), nullable=False, server_default='GREEN'))
    op.add_column('events', sa.Column('warning_reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f('ix_events_warning_level'), 'events', ['warning_level'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_events_warning_level'), table_name='events')
    op.drop_column('events', 'warning_reasons')
    op.drop_column('events', 'warning_level')
    op.execute("DROP TYPE IF EXISTS warning_level")
