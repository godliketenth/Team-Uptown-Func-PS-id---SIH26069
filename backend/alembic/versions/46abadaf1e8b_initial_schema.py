"""initial schema

Revision ID: 46abadaf1e8b
Revises: 
Create Date: 2026-09-22 17:47:54.365127
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '46abadaf1e8b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS powers every ST_DWithin radius query in the pipeline and API.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # NB: the geom GiST indexes (idx_events_geom / idx_reports_geom) are emitted
    # by GeoAlchemy2's own CREATE TABLE hook, so they are not listed here.
    op.create_table('events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.Enum('RAIN', 'FLOOD', 'THUNDERSTORM', 'HEATWAVE', 'FOG', 'DUST_STORM', 'STRONG_WIND', name='event_type'), nullable=False),
    sa.Column('status', sa.Enum('DETECTED', 'CORROBORATING', 'NEEDS_REVIEW', 'VERIFIED', 'REJECTED', 'RESOLVED', name='event_status'), nullable=False),
    sa.Column('center_latitude', sa.Float(), nullable=False),
    sa.Column('center_longitude', sa.Float(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.Column('state', sa.Text(), nullable=True),
    sa.Column('district', sa.Text(), nullable=True),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
    sa.Column('report_count', sa.Integer(), nullable=False),
    sa.Column('source_count', sa.Integer(), nullable=False),
    sa.Column('evidence_score', sa.Float(), nullable=False),
    sa.Column('corroboration_score', sa.Float(), nullable=False),
    sa.Column('severity', sa.Enum('LOW', 'MODERATE', 'HIGH', 'SEVERE', name='severity'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_events_district'), 'events', ['district'], unique=False)
    op.create_index(op.f('ix_events_event_type'), 'events', ['event_type'], unique=False)
    op.create_index(op.f('ix_events_last_updated'), 'events', ['last_updated'], unique=False)
    op.create_index(op.f('ix_events_start_time'), 'events', ['start_time'], unique=False)
    op.create_index(op.f('ix_events_state'), 'events', ['state'], unique=False)
    op.create_index(op.f('ix_events_status'), 'events', ['status'], unique=False)
    op.create_table('sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('source_type', sa.Enum('GOVERNMENT', 'WEATHER_API', 'CITIZEN', 'SOCIAL', 'WEB_RSS', 'SATELLITE', name='source_type'), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', 'ERROR', name='source_status'), nullable=False),
    sa.Column('poll_interval_seconds', sa.Integer(), nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=True),
    sa.Column('role', sa.Enum('PUBLIC_USER', 'ANALYST', 'VERIFIER', 'ADMIN', name='user_role'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_email', sa.Text(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=True),
    sa.Column('target_id', sa.Text(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_table('event_status_history',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('old_status', sa.Text(), nullable=True),
    sa.Column('new_status', sa.Text(), nullable=False),
    sa.Column('changed_by', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_status_history_event_id'), 'event_status_history', ['event_id'], unique=False)
    op.create_table('raw_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=True),
    sa.Column('source_type', sa.Enum('GOVERNMENT', 'WEATHER_API', 'CITIZEN', 'SOCIAL', 'WEB_RSS', 'SATELLITE', name='source_type'), nullable=False),
    sa.Column('external_id', sa.Text(), nullable=True),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_raw_events_collected_at'), 'raw_events', ['collected_at'], unique=False)
    op.create_index(op.f('ix_raw_events_external_id'), 'raw_events', ['external_id'], unique=False)
    op.create_index(op.f('ix_raw_events_source_id'), 'raw_events', ['source_id'], unique=False)
    op.create_index(op.f('ix_raw_events_source_type'), 'raw_events', ['source_type'], unique=False)
    op.create_table('reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('raw_event_id', sa.UUID(), nullable=True),
    sa.Column('source_id', sa.UUID(), nullable=True),
    sa.Column('source_type', sa.Enum('GOVERNMENT', 'WEATHER_API', 'CITIZEN', 'SOCIAL', 'WEB_RSS', 'SATELLITE', name='source_type'), nullable=False),
    sa.Column('external_id', sa.Text(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('normalized_text', sa.Text(), nullable=True),
    sa.Column('text_hash', sa.String(length=64), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('geom', geoalchemy2.types.Geography(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeogFromText', name='geography'), nullable=True),
    sa.Column('city', sa.Text(), nullable=True),
    sa.Column('district', sa.Text(), nullable=True),
    sa.Column('state', sa.Text(), nullable=True),
    sa.Column('location_confidence', sa.Float(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('event_type_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('predicted_event_type', sa.Text(), nullable=True),
    sa.Column('weather_corroboration', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reliability_score', sa.Float(), nullable=True),
    sa.Column('insufficient_evidence', sa.Boolean(), nullable=False),
    sa.Column('duplicate_of_report_id', sa.UUID(), nullable=True),
    sa.Column('dedup_method', sa.Text(), nullable=True),
    sa.Column('event_id', sa.UUID(), nullable=True),
    sa.Column('media', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('processing_state', sa.Enum('RECEIVED', 'NORMALIZED', 'ENRICHED', 'CLASSIFIED', 'DEDUPLICATED', 'EVENT_ASSIGNED', name='processing_state'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['duplicate_of_report_id'], ['reports.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['raw_event_id'], ['raw_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reports_city'), 'reports', ['city'], unique=False)
    op.create_index(op.f('ix_reports_district'), 'reports', ['district'], unique=False)
    op.create_index(op.f('ix_reports_event_id'), 'reports', ['event_id'], unique=False)
    op.create_index(op.f('ix_reports_observed_at'), 'reports', ['observed_at'], unique=False)
    op.create_index(op.f('ix_reports_predicted_event_type'), 'reports', ['predicted_event_type'], unique=False)
    op.create_index(op.f('ix_reports_processing_state'), 'reports', ['processing_state'], unique=False)
    op.create_index(op.f('ix_reports_source_type'), 'reports', ['source_type'], unique=False)
    op.create_index(op.f('ix_reports_state'), 'reports', ['state'], unique=False)
    op.create_index(op.f('ix_reports_text_hash'), 'reports', ['text_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reports_text_hash'), table_name='reports')
    op.drop_index(op.f('ix_reports_state'), table_name='reports')
    op.drop_index(op.f('ix_reports_source_type'), table_name='reports')
    op.drop_index(op.f('ix_reports_processing_state'), table_name='reports')
    op.drop_index(op.f('ix_reports_predicted_event_type'), table_name='reports')
    op.drop_index(op.f('ix_reports_observed_at'), table_name='reports')
    op.drop_index(op.f('ix_reports_event_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_district'), table_name='reports')
    op.drop_index(op.f('ix_reports_city'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_raw_events_source_type'), table_name='raw_events')
    op.drop_index(op.f('ix_raw_events_source_id'), table_name='raw_events')
    op.drop_index(op.f('ix_raw_events_external_id'), table_name='raw_events')
    op.drop_index(op.f('ix_raw_events_collected_at'), table_name='raw_events')
    op.drop_table('raw_events')
    op.drop_index(op.f('ix_event_status_history_event_id'), table_name='event_status_history')
    op.drop_table('event_status_history')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('sources')
    op.drop_index(op.f('ix_events_status'), table_name='events')
    op.drop_index(op.f('ix_events_state'), table_name='events')
    op.drop_index(op.f('ix_events_start_time'), table_name='events')
    op.drop_index(op.f('ix_events_last_updated'), table_name='events')
    op.drop_index(op.f('ix_events_event_type'), table_name='events')
    op.drop_index(op.f('ix_events_district'), table_name='events')
    op.drop_table('events')
