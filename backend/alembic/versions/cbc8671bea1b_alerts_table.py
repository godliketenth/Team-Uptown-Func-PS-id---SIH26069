"""alerts table

Revision ID: cbc8671bea1b
Revises: b662257f4b01
Create Date: 2026-09-29 07:32:42.602170
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = 'cbc8671bea1b'
down_revision = 'b662257f4b01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    alert_status = postgresql.ENUM(
        'ACTIVE', 'ACKNOWLEDGED', 'CLOSED', name='alert_status'
    )
    alert_status.create(op.get_bind(), checkfirst=True)
    op.create_table('alerts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('level', postgresql.ENUM('GREEN', 'YELLOW', 'ORANGE', 'RED', name='warning_level', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'ACKNOWLEDGED', 'CLOSED', name='alert_status', create_type=False), nullable=False),
    sa.Column('event_type', postgresql.ENUM('RAIN', 'FLOOD', 'THUNDERSTORM', 'HEATWAVE', 'FOG', 'DUST_STORM', 'STRONG_WIND', name='event_type', create_type=False), nullable=False),
    sa.Column('state', sa.Text(), nullable=True),
    sa.Column('district', sa.Text(), nullable=True),
    sa.Column('center_latitude', sa.Float(), nullable=True),
    sa.Column('center_longitude', sa.Float(), nullable=True),
    sa.Column('headline', sa.Text(), nullable=False),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('evidence_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('raised_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('previous_level', sa.Text(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by', sa.Text(), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alerts_district'), 'alerts', ['district'], unique=False)
    op.create_index(op.f('ix_alerts_event_id'), 'alerts', ['event_id'], unique=False)
    op.create_index(op.f('ix_alerts_level'), 'alerts', ['level'], unique=False)
    op.create_index(op.f('ix_alerts_raised_at'), 'alerts', ['raised_at'], unique=False)
    op.create_index(op.f('ix_alerts_state'), 'alerts', ['state'], unique=False)
    op.create_index(op.f('ix_alerts_status'), 'alerts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alerts_status'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_state'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_raised_at'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_level'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_event_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_district'), table_name='alerts')
    op.drop_table('alerts')
    op.execute("DROP TYPE IF EXISTS alert_status")
