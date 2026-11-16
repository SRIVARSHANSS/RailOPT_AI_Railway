"""Database-backed ScenarioStore (Phase 8): same interface, state persisted.

Computation stays in memory (the parent class); every mutation (reset, event, recommendation,
decision) is written through to the database inside the store's lock, and the current scenario
is reloaded from the database when the API starts.

scenario_version = '<boot id>-<revision>'. The boot id is stored with the scenario, so an API
restart keeps the version: the state, the recommendations and their ids all survive, so results
a client cached for that version are still valid. Reset, events and decisions still bump the
revision (a reset keeps counting, so a version is never reused).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.core.store import Recommendation, ScenarioStore
from app.db import models as m
from app.services.simulator import Disruption

log = logging.getLogger("railopt.store")


def _pairs(d: dict) -> list:
    return [[a, b, v] for (a, b), v in d.items()]


def _unpairs(rows: list) -> dict:
    return {(a, b): v for a, b, v in rows or []}


def _json(payload) -> dict:
    """Plain JSON (numpy numbers and the like become ints/floats/strings)."""
    return json.loads(json.dumps(payload, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


@dataclass
class DbScenarioStore(ScenarioStore):
    _sf: sessionmaker | None = field(default=None, repr=False)
    _row_id: int | None = field(default=None, repr=False)

    # ---- load / save ---------------------------------------------------------------------
    @classmethod
    def open(cls, sf: sessionmaker, boot=None, custom_loader=None) -> "DbScenarioStore":
        """Load the current scenario, or create one with `boot(store)` on an empty database."""
        store = cls(_sf=sf, custom_loader=custom_loader)
        with sf() as db:
            row = db.scalars(select(m.Scenario).where(m.Scenario.is_current.is_(True))
                             .order_by(m.Scenario.id.desc())).first()
            if row is not None:
                store._load(db, row)
                log.info("scenario %s loaded from the database (version %s)", row.id, store.version)
                return store
        if boot is not None:
            boot(store)                          # calls reset(): writes the first scenario row
        else:
            store._new_row(None)
        return store

    def _load(self, db, row: m.Scenario) -> None:
        day = None
        if row.mode == "replay":
            from app.services.realdata.replay import get_day
            day = get_day(row.replay_date)
        self._row_id = row.id
        self.timetable, self.mode, self.replay_date, self._day = row.timetable, row.mode, row.replay_date, day
        self.boot_id, self.revision = row.boot_id, row.revision
        self.applied_recommendation, self.plan_basis_at = row.applied_recommendation, row.plan_basis_at
        self.plan_basis_events = list(row.plan_basis_events or [])
        self.holds, self.route_overrides = _unpairs(row.holds), _unpairs(row.route_overrides)
        self.previous_holds, self.previous_overrides = _unpairs(row.previous_holds), _unpairs(row.previous_overrides)
        self.events = [Disruption(e.event_id, e.event_type, e.train_id, e.location, e.start_min, e.duration_min)
                       for e in db.scalars(select(m.Event).where(m.Event.scenario_id == row.id).order_by(m.Event.id))]
        self.recommendations = {}
        for r in db.scalars(select(m.Recommendation).where(m.Recommendation.scenario_id == row.id)
                            .order_by(m.Recommendation.id)):
            self.recommendations[r.rec_id] = Recommendation(
                r.rec_id, r.at_min, r.strategy, _unpairs(r.holds), _unpairs(r.route_overrides), r.payload,
                decision=r.decision, known_event_ids=list(r.known_event_ids or []))
        self.decision_log = [
            {"recommendation_id": d.rec_id, "decision": d.decision, "strategy": d.strategy, "at": d.at_min,
             "replaces": d.replaces, "logged_at_utc": d.decided_at.isoformat(timespec="seconds"),
             "decided_by": d.user_email}
            for d in db.scalars(select(m.Decision).where(m.Decision.scenario_id == row.id).order_by(m.Decision.id))]

    def _state(self) -> dict:
        return {"timetable": self.timetable, "mode": self.mode, "replay_date": self.replay_date,
                "boot_id": self.boot_id, "revision": self.revision,
                "applied_recommendation": self.applied_recommendation, "plan_basis_at": self.plan_basis_at,
                "plan_basis_events": list(self.plan_basis_events), "holds": _pairs(self.holds),
                "route_overrides": _pairs(self.route_overrides), "previous_holds": _pairs(self.previous_holds),
                "previous_overrides": _pairs(self.previous_overrides)}

    def _new_row(self, actor: dict | None) -> None:
        with self._sf() as db, db.begin():
            db.execute(update(m.Scenario).where(m.Scenario.is_current.is_(True)).values(is_current=False))
            row = m.Scenario(is_current=True, created_by=(actor or {}).get("id"), **self._state())
            db.add(row)
            db.flush()
            self._row_id = row.id

    def _save_row(self, db) -> None:
        db.execute(update(m.Scenario).where(m.Scenario.id == self._row_id).values(**self._state()))

    # ---- mutations: compute in memory, then write through ----------------------------------
    def reset(self, timetable: str, mode: str = "live", date: str | None = None, actor: dict | None = None) -> None:
        with self._lock:
            super().reset(timetable, mode, date, actor=actor)
            self._new_row(actor)

    def add_event(self, event_type, train_id, location, start, duration, prefix="E", actor=None):
        with self._lock:
            event = super().add_event(event_type, train_id, location, start, duration, prefix, actor=actor)
            with self._sf() as db, db.begin():
                db.add(m.Event(scenario_id=self._row_id, event_id=event.event_id, event_type=event.event_type,
                               train_id=event.train_id, location=event.location, start_min=event.start,
                               duration_min=event.duration, created_by=(actor or {}).get("id")))
                self._save_row(db)
            return event

    def add_recommendation(self, at, strategy, holds, route_overrides, payload, known_event_ids=None, actor=None):
        with self._lock:
            rec = super().add_recommendation(at, strategy, holds, route_overrides, payload, known_event_ids, actor=actor)
            with self._sf() as db, db.begin():
                db.add(m.Recommendation(scenario_id=self._row_id, rec_id=rec.rec_id, at_min=rec.at,
                                        strategy=rec.strategy, holds=_pairs(rec.holds),
                                        route_overrides=_pairs(rec.route_overrides),
                                        known_event_ids=list(rec.known_event_ids), payload=_json(rec.payload),
                                        created_by=(actor or {}).get("id")))
            return rec

    def save_payload(self, rec_id: str) -> None:
        with self._lock, self._sf() as db, db.begin():
            db.execute(update(m.Recommendation)
                       .where(m.Recommendation.scenario_id == self._row_id, m.Recommendation.rec_id == rec_id)
                       .values(payload=_json(self.recommendations[rec_id].payload)))

    def decide(self, rec_id: str, decision: str, actor: dict | None = None):
        with self._lock:
            rec = super().decide(rec_id, decision, actor=actor)
            entry = self.decision_log[-1]
            with self._sf() as db, db.begin():
                row = db.scalars(select(m.Recommendation).where(m.Recommendation.scenario_id == self._row_id,
                                                                m.Recommendation.rec_id == rec_id)).one()
                row.decision = decision
                db.add(m.Decision(scenario_id=self._row_id, recommendation_id=row.id, rec_id=rec_id,
                                  decision=decision, strategy=rec.strategy, at_min=rec.at,
                                  replaces=entry["replaces"], user_id=(actor or {}).get("id"),
                                  user_email=(actor or {}).get("email")))
                self._save_row(db)
            return rec


def _boot(store: DbScenarioStore) -> None:
    """First start on an empty database: the same default as boot_store() (REAL demo day,
    RAILOPT_BOOT=simulated for the reference corridor)."""
    import os
    store.boot_id = uuid.uuid4().hex[:8]
    if os.environ.get("RAILOPT_BOOT", "replay").strip().lower() != "simulated":
        try:
            from app.services.realdata.replay import DEMO_DAY
            store.reset("dg_mdu", "replay", DEMO_DAY)
            return
        except (OSError, ValueError) as exc:
            log.warning("REAL demo day not available (%s); starting on the SIMULATED reference corridor", exc)
    store.reset("reference")


def open_db_store() -> DbScenarioStore:
    from app.db.session import session_factory
    from app.services import netadmin
    return DbScenarioStore.open(session_factory(), boot=_boot, custom_loader=netadmin.custom_network)
