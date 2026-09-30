"""authorities and alert deliveries

Revision ID: 77c368082620
Revises: cbc8671bea1b
Create Date: 2026-09-29 07:39:29.386633
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '77c368082620'
down_revision = 'cbc8671bea1b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, values in (
        ("authority_level", ("NATIONAL", "STATE", "DISTRICT")),
        ("delivery_channel", ("WEBHOOK", "EMAIL", "SMS")),
        ("delivery_status", ("PENDING", "SENT", "FAILED", "SIMULATED")),
    ):
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)
    op.create_table('authorities',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('level', postgresql.ENUM('NATIONAL', 'STATE', 'DISTRICT', name='authority_level', create_type=False), nullable=False),
    sa.Column('state', sa.Text(), nullable=True),
    sa.Column('district', sa.Text(), nullable=True),
    sa.Column('contact_email', sa.Text(), nullable=True),
    sa.Column('webhook_url', sa.Text(), nullable=True),
    sa.Column('phone', sa.Text(), nullable=True),
    sa.Column('event_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('min_level', postgresql.ENUM('GREEN', 'YELLOW', 'ORANGE', 'RED', name='warning_level', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'PAUSED', 'ERROR', name='source_status', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_authorities_district'), 'authorities', ['district'], unique=False)
    op.create_index(op.f('ix_authorities_level'), 'authorities', ['level'], unique=False)
    op.create_index(op.f('ix_authorities_state'), 'authorities', ['state'], unique=False)
    op.create_table('alert_deliveries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('alert_id', sa.UUID(), nullable=False),
    sa.Column('authority_id', sa.UUID(), nullable=False),
    sa.Column('channel', postgresql.ENUM('WEBHOOK', 'EMAIL', 'SMS', name='delivery_channel', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDING', 'SENT', 'FAILED', 'SIMULATED', name='delivery_status', create_type=False), nullable=False),
    sa.Column('target', sa.Text(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('response_code', sa.Integer(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['authority_id'], ['authorities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alert_deliveries_alert_id'), 'alert_deliveries', ['alert_id'], unique=False)
    op.create_index(op.f('ix_alert_deliveries_authority_id'), 'alert_deliveries', ['authority_id'], unique=False)
    op.create_index(op.f('ix_alert_deliveries_queued_at'), 'alert_deliveries', ['queued_at'], unique=False)
    op.create_index(op.f('ix_alert_deliveries_status'), 'alert_deliveries', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alert_deliveries_status'), table_name='alert_deliveries')
    op.drop_index(op.f('ix_alert_deliveries_queued_at'), table_name='alert_deliveries')
    op.drop_index(op.f('ix_alert_deliveries_authority_id'), table_name='alert_deliveries')
    op.drop_index(op.f('ix_alert_deliveries_alert_id'), table_name='alert_deliveries')
    op.drop_table('alert_deliveries')
    op.drop_index(op.f('ix_authorities_state'), table_name='authorities')
    op.drop_index(op.f('ix_authorities_level'), table_name='authorities')
    op.drop_index(op.f('ix_authorities_district'), table_name='authorities')
    op.drop_table('authorities')
    for name in ("delivery_status", "delivery_channel", "authority_level"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
