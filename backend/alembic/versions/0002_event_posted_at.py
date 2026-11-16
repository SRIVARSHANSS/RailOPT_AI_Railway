"""Sim clock at which an event was posted (alert history, Conflicts and Alerts page).

Revision ID: 0002_event_posted_at
Revises: 0001_initial
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_event_posted_at"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("posted_at_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_column("posted_at_min")
