"""Phase 8: the scenario survives an API restart; Alembic migrations run up and down.

A "restart" = a second DbScenarioStore opened on the same database file, as the API does on
start. Migrations are tested on a throwaway SQLite file; the same test runs on PostgreSQL when
TEST_DATABASE_URL points at a throwaway database (pytest -m postgres)."""
import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.db_store import DbScenarioStore
from app.core.store import get_store
from app.db import models as m
from app.db.session import make_engine
from app.main import app
from app.services.network import parse_time
from tests.conftest import BACKEND

STOP = {"event_type": "STOPPAGE", "train_id": "T101", "location": "S_BC", "start_time": "10:03", "duration_min": 15}


def alembic_cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))   # configparser: a literal % (e.g. in a password)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'railopt.sqlite3').as_posix()}"
    command.upgrade(alembic_cfg(url), "head")
    return url


def open_store(url: str) -> DbScenarioStore:
    sf = sessionmaker(bind=make_engine(url), expire_on_commit=False)
    return DbScenarioStore.open(sf, boot=lambda s: s.reset("reference"))


def state(store):
    return (store.version, store.timetable, store.mode, [vars(e) for e in store.events], sorted(store.holds.items()),
            sorted(store.route_overrides.items()), store.applied_recommendation, store.plan_basis_at,
            store.plan_basis_events, sorted(store.previous_holds.items()),
            {k: (r.strategy, r.at, r.decision, sorted(r.holds.items())) for k, r in store.recommendations.items()},
            [{k: v for k, v in d.items() if k != "logged_at_utc"} for d in store.decision_log])


def test_scenario_survives_restart(db_url):
    a = open_store(db_url)
    assert a.version.endswith("-1") and a.timetable == "reference"
    app.dependency_overrides[get_store] = lambda: a
    try:
        with TestClient(app) as c:
            c.post("/api/events", json=STOP)
            o = c.post("/api/optimize", json={"at": "10:03"}).json()
            rec_id = o["recommendation"]["recommendation_id"]
            c.post(f"/api/recommendation/{rec_id}/decision", json={"decision": "accept"})
            before_tl = c.get("/api/timeline").json()
    finally:
        app.dependency_overrides.pop(get_store, None)
    assert a.decision_log[-1]["decided_by"] == "pytest-controller@local"

    b = open_store(db_url)                                   # the API restarts
    assert state(b) == state(a)
    assert b.version == a.version                            # same state -> same version (cached results stay valid)
    assert b.recommendations[rec_id].payload["explanation"]["plain_text"]   # completed payload was saved
    assert b.actual().occupancies == a.actual().occupancies
    app.dependency_overrides[get_store] = lambda: b
    try:
        with TestClient(app) as c:
            assert c.get("/api/timeline").json() == before_tl
            e2 = c.post("/api/events", json={**STOP, "event_type": "DELAY", "train_id": "T202", "location": "A",
                                             "start_time": "10:05", "duration_min": 5}).json()
            assert e2["event"]["event_id"] == "E2"
    finally:
        app.dependency_overrides.pop(get_store, None)
    rev = b.revision
    b.reset("full_day")
    assert b.version == f"{b.boot_id}-{rev + 1}" and not b.events
    c2 = open_store(db_url)
    assert c2.version == b.version and c2.timetable == "full_day" and c2.events == []

    sf = sessionmaker(bind=make_engine(db_url))
    with sf() as db:                                         # history of the earlier scenario is kept
        assert db.scalars(select(m.Scenario).where(m.Scenario.is_current.is_(True))).all()[0].timetable == "full_day"
        dec = db.scalars(select(m.Decision)).one()
        assert dec.rec_id == rec_id and dec.decision == "accept" and dec.user_email == "pytest-controller@local"
        assert len(db.scalars(select(m.Event)).all()) == 2


def test_replay_scenario_survives_restart(db_url):
    from app.services.network.model import REAL_DATA_DIR
    if not (REAL_DATA_DIR / "records.csv").exists():
        pytest.skip("REAL extract missing")
    a = open_store(db_url)
    a.reset("dg_mdu", "replay", "2024-09-12")
    a.add_event("STOPPAGE", "R22627", "S_ABI_KQN", parse_time("08:53"), 25)
    b = open_store(db_url)
    assert b.is_replay and b.replay_date == "2024-09-12" and b.version == a.version
    assert b.label() == "HYPOTHETICAL on a real recorded day"
    assert b.actual().occupancies == a.actual().occupancies


# ---- migrations ----------------------------------------------------------------------------------
def _migrate_up_down(url: str) -> None:
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "head")
    engine = make_engine(url)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), m.Base.metadata) == []   # models == migrations
    tables = set(inspect(engine).get_table_names())
    assert {"users", "scenarios", "events", "recommendations", "decisions", "audit_log"} <= tables
    command.downgrade(cfg, "base")
    assert set(inspect(make_engine(url)).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")                            # and up again
    assert "audit_log" in inspect(make_engine(url)).get_table_names()
    command.downgrade(cfg, "base")


def test_migrations_up_and_down_sqlite(tmp_path):
    _migrate_up_down(f"sqlite:///{(tmp_path / 'mig.sqlite3').as_posix()}")


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to a throwaway PostgreSQL DB")
def test_migrations_up_and_down_postgres():
    url = os.environ["TEST_DATABASE_URL"]
    assert "test" in url.rsplit("/", 1)[-1], "TEST_DATABASE_URL must name a throwaway database (name contains 'test')"
    _migrate_up_down(url)
