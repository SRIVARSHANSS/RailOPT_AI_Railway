"""SQLAlchemy 2 models (Phase 8). Migrations: backend/alembic (never create_all in production).

Scenario state is persisted so it survives an API restart; computation stays in memory
(app/core/store.py). Every scenario row keeps its events, recommendations and decisions, so the
history of earlier scenarios (before a reset) stays in the database. The custom_* tables hold
the admin-editable SIMULATED corridor ("custom" timetable); reference and full_day stay as the
committed CSVs (tests, demo and evaluation depend on them)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


ROLES = ("ADMIN", "CONTROLLER", "ANALYST")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)   # +1 on logout / deactivate / reset
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    timetable: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(10))
    replay_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    boot_id: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    applied_recommendation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan_basis_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_basis_events: Mapped[list] = mapped_column(JSON, default=list)
    holds: Mapped[list] = mapped_column(JSON, default=list)               # [[train, station, minute]]
    route_overrides: Mapped[list] = mapped_column(JSON, default=list)     # [[train, station, section]]
    previous_holds: Mapped[list] = mapped_column(JSON, default=list)
    previous_overrides: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("scenario_id", "event_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(30))
    train_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location: Mapped[str] = mapped_column(String(40))
    start_min: Mapped[int] = mapped_column(Integer)
    duration_min: Mapped[int] = mapped_column(Integer)
    posted_at_min: Mapped[int | None] = mapped_column(Integer, nullable=True)   # sim clock when posted
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("scenario_id", "rec_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), index=True)
    rec_id: Mapped[str] = mapped_column(String(20))
    at_min: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(30))
    holds: Mapped[list] = mapped_column(JSON, default=list)
    route_overrides: Mapped[list] = mapped_column(JSON, default=list)
    known_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), index=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"))
    rec_id: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(10))
    strategy: Mapped[str] = mapped_column(String(30))
    at_min: Mapped[int] = mapped_column(Integer)
    replaces: Mapped[str | None] = mapped_column(String(20), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_email_action_at", "email", "action", "at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---- admin-editable SIMULATED corridor ("custom" timetable); values as in the CSV files ----
class CustomStation(Base):
    __tablename__ = "custom_stations"
    pos: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_code: Mapped[str] = mapped_column(String(20))
    station_name: Mapped[str] = mapped_column(String(120))
    km_from_start: Mapped[str] = mapped_column(String(20))
    platforms: Mapped[str] = mapped_column(String(10))
    is_junction: Mapped[str] = mapped_column(String(5))


class CustomSection(Base):
    __tablename__ = "custom_sections"
    pos: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[str] = mapped_column(String(40))
    from_station: Mapped[str] = mapped_column(String(20))
    to_station: Mapped[str] = mapped_column(String(20))
    length_km: Mapped[str] = mapped_column(String(20))
    tracks: Mapped[str] = mapped_column(String(10))
    min_run_min: Mapped[str] = mapped_column(String(10))
    min_headway_min: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))


class CustomTrain(Base):
    __tablename__ = "custom_trains"
    pos: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[str] = mapped_column(String(20))
    train_no: Mapped[str] = mapped_column(String(20))
    train_name: Mapped[str] = mapped_column(String(120))
    train_type: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(5))
    runs_on: Mapped[str] = mapped_column(String(40))


class CustomStop(Base):
    __tablename__ = "custom_schedule"
    pos: Mapped[int] = mapped_column(Integer, primary_key=True)
    train_id: Mapped[str] = mapped_column(String(20))
    station_code: Mapped[str] = mapped_column(String(20))
    stop_seq: Mapped[str] = mapped_column(String(5))
    sched_arr: Mapped[str] = mapped_column(String(5))
    sched_dep: Mapped[str] = mapped_column(String(5))
