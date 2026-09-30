"""status history clock timestamp

Revision ID: a9e3145100ff
Revises: 46abadaf1e8b
Create Date: 2026-09-22 18:17:25.582496
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2


revision = 'a9e3145100ff'
down_revision = '46abadaf1e8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # now() is the transaction timestamp: two status changes committed in the
    # same transaction would tie and the lifecycle would read out of order.
    op.execute(
        "ALTER TABLE event_status_history "
        "ALTER COLUMN created_at SET DEFAULT clock_timestamp()"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE event_status_history ALTER COLUMN created_at SET DEFAULT now()")
