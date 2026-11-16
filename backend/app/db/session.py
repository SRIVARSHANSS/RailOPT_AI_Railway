"""Engine and sessions. The engine is created lazily, so importing the app (tests) never
connects to a database; tests install their own engine with set_engine()."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_engine: Engine | None = None
_factory: sessionmaker | None = None


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kw = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool          # one shared in-memory database
        return create_engine(url, **kw)
    return create_engine(url, pool_pre_ping=True)


def set_engine(engine: Engine | None) -> None:
    global _engine, _factory
    _engine = engine
    _factory = sessionmaker(bind=engine, expire_on_commit=False) if engine is not None else None


def get_engine() -> Engine:
    if _engine is None:
        from app.core.config import get_settings
        set_engine(make_engine(get_settings().database_url))
    return _engine


def session_factory() -> sessionmaker:
    get_engine()
    return _factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
