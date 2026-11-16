"""Phase 8 initial schema: users, scenarios, events, recommendations, decisions, audit_log,
and the admin-editable custom corridor tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_login_at", TS, nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("timetable", sa.String(40), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("replay_date", sa.String(10), nullable=True),
        sa.Column("boot_id", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("applied_recommendation", sa.String(20), nullable=True),
        sa.Column("plan_basis_at", sa.Integer(), nullable=True),
        sa.Column("plan_basis_events", sa.JSON(), nullable=False),
        sa.Column("holds", sa.JSON(), nullable=False),
        sa.Column("route_overrides", sa.JSON(), nullable=False),
        sa.Column("previous_holds", sa.JSON(), nullable=False),
        sa.Column("previous_overrides", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_scenarios_is_current", "scenarios", ["is_current"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("event_id", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("train_id", sa.String(20), nullable=True),
        sa.Column("location", sa.String(40), nullable=False),
        sa.Column("start_min", sa.Integer(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("scenario_id", "event_id"),
    )
    op.create_index("ix_events_scenario_id", "events", ["scenario_id"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("rec_id", sa.String(20), nullable=False),
        sa.Column("at_min", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(30), nullable=False),
        sa.Column("holds", sa.JSON(), nullable=False),
        sa.Column("route_overrides", sa.JSON(), nullable=False),
        sa.Column("known_event_ids", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(10), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("scenario_id", "rec_id"),
    )
    op.create_index("ix_recommendations_scenario_id", "recommendations", ["scenario_id"])

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id"), nullable=False),
        sa.Column("rec_id", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("strategy", sa.String(30), nullable=False),
        sa.Column("at_min", sa.Integer(), nullable=False),
        sa.Column("replaces", sa.String(20), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_email", sa.String(254), nullable=True),
        sa.Column("decided_at", TS, nullable=False),
    )
    op.create_index("ix_decisions_scenario_id", "decisions", ["scenario_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", TS, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_email_action_at", "audit_log", ["email", "action", "at"])

    op.create_table(
        "custom_stations",
        sa.Column("pos", sa.Integer(), primary_key=True),
        sa.Column("station_code", sa.String(20), nullable=False),
        sa.Column("station_name", sa.String(120), nullable=False),
        sa.Column("km_from_start", sa.String(20), nullable=False),
        sa.Column("platforms", sa.String(10), nullable=False),
        sa.Column("is_junction", sa.String(5), nullable=False),
    )
    op.create_table(
        "custom_sections",
        sa.Column("pos", sa.Integer(), primary_key=True),
        sa.Column("section_id", sa.String(40), nullable=False),
        sa.Column("from_station", sa.String(20), nullable=False),
        sa.Column("to_station", sa.String(20), nullable=False),
        sa.Column("length_km", sa.String(20), nullable=False),
        sa.Column("tracks", sa.String(10), nullable=False),
        sa.Column("min_run_min", sa.String(10), nullable=False),
        sa.Column("min_headway_min", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
    )
    op.create_table(
        "custom_trains",
        sa.Column("pos", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.String(20), nullable=False),
        sa.Column("train_no", sa.String(20), nullable=False),
        sa.Column("train_name", sa.String(120), nullable=False),
        sa.Column("train_type", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(5), nullable=False),
        sa.Column("runs_on", sa.String(40), nullable=False),
    )
    op.create_table(
        "custom_schedule",
        sa.Column("pos", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.String(20), nullable=False),
        sa.Column("station_code", sa.String(20), nullable=False),
        sa.Column("stop_seq", sa.String(5), nullable=False),
        sa.Column("sched_arr", sa.String(5), nullable=False),
        sa.Column("sched_dep", sa.String(5), nullable=False),
    )


def downgrade() -> None:
    for t in ("custom_schedule", "custom_trains", "custom_sections", "custom_stations"):
        op.drop_table(t)
    op.drop_index("ix_audit_email_action_at", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_decisions_scenario_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_recommendations_scenario_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_events_scenario_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_scenarios_is_current", table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
