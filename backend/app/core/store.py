"""In-memory scenario state for the API (Phase 8 replaces this with PostgreSQL).

Everything the API needs about "the current scenario" goes through
`ScenarioStore`, so swapping the storage later does not touch the routes.

Knowledge is time-aware (same no-leakage rule as Phase 2):
* STOPPAGE and DELAY are surprises: known only when the clock `at` has
  reached their start time.
* TRACK_UNAVAILABLE is planned maintenance: known as soon as it is posted.
* PLATFORM_UNAVAILABLE follows the surprise rule (and is not modelled yet).
The simulated movement of trains (`actual`) always uses every posted event,
because that is what really happens; only detection, prediction and
re-planning are limited to what is known at `at`.

All data here is SIMULATED.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.network import RailNetwork, load_network
from app.services.simulator import Disruption, SimResult, simulate

log = logging.getLogger("railopt.decisions")

PLANNED_EVENT_TYPES = {"TRACK_UNAVAILABLE"}      # known from the moment they are posted


@dataclass
class Recommendation:
    rec_id: str
    at: int
    strategy: str
    holds: dict[tuple[str, str], int]
    route_overrides: dict[tuple[str, str], str]
    payload: dict                                 # the response body, kept for the record
    decision: str | None = None                   # accept | reject
    known_event_ids: list[str] = field(default_factory=list)   # what the optimizer knew


@dataclass
class ScenarioStore:
    timetable: str = "reference"
    events: list[Disruption] = field(default_factory=list)
    holds: dict[tuple[str, str], int] = field(default_factory=dict)
    route_overrides: dict[tuple[str, str], str] = field(default_factory=dict)
    applied_recommendation: str | None = None
    plan_basis_at: int | None = None              # clock time the accepted plan was computed for
    plan_basis_events: list[str] = field(default_factory=list)  # events it knew about
    previous_holds: dict[tuple[str, str], int] = field(default_factory=dict)       # plan the current one replaced
    previous_overrides: dict[tuple[str, str], str] = field(default_factory=dict)
    recommendations: dict[str, Recommendation] = field(default_factory=dict)
    decision_log: list[dict] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _nets: dict[str, RailNetwork] = field(default_factory=dict, repr=False)

    # ---- network ---------------------------------------------------------------
    def network(self, timetable: str | None = None) -> RailNetwork:
        name = timetable or self.timetable
        if name not in self._nets:
            self._nets[name] = load_network(timetable=name)
        return self._nets[name]

    # ---- scenario ----------------------------------------------------------------
    def reset(self, timetable: str) -> None:
        self.network(timetable)                 # validates the name
        with self._lock:
            self.timetable = timetable
            self.events.clear()
            self.holds.clear()
            self.route_overrides.clear()
            self.applied_recommendation = None
            self.plan_basis_at = None
            self.plan_basis_events = []
            self.previous_holds = {}
            self.previous_overrides = {}
            self.recommendations.clear()
            self.decision_log.clear()

    def add_event(self, event_type: str, train_id: str | None, location: str,
                  start: int, duration: int, prefix: str = "E") -> Disruption:
        with self._lock:
            n = sum(1 for e in self.events if e.event_id.startswith(prefix)) + 1
            event = Disruption(f"{prefix}{n}", event_type, train_id, location, start, duration)
            self.events.append(event)
            return event

    def known_events(self, at: int) -> list[Disruption]:
        """Events the controller knows about at clock time `at`."""
        return [e for e in self.events if e.event_type in PLANNED_EVENT_TYPES or e.start <= at]

    def actual(self) -> SimResult:
        """What happens: every posted event, plus the accepted plan (holds / reroutes)."""
        return simulate(self.network(), self.events, route_overrides=self.route_overrides, holds=self.holds)

    def plan_status(self, at: int | None = None) -> dict:
        """Is the accepted plan stale? It is when an event is known now that the plan's
        optimizer run did not know (a surprise that has started since, or anything posted
        after it). Without `at`, every posted event counts."""
        if self.applied_recommendation is None:
            return {"applied": None, "stale": False, "new_events": [], "basis_at": None}
        known = self.events if at is None else self.known_events(at)
        new = [e.event_id for e in known if e.event_id not in self.plan_basis_events]
        return {"applied": self.applied_recommendation, "stale": bool(new), "new_events": new,
                "basis_at": self.plan_basis_at}

    def copy_for_whatif(self) -> "ScenarioStore":
        """Independent copy of events + accepted plan (networks are shared, read-only)."""
        with self._lock:
            return ScenarioStore(
                timetable=self.timetable, events=list(self.events), holds=dict(self.holds),
                route_overrides=dict(self.route_overrides), applied_recommendation=self.applied_recommendation,
                plan_basis_at=self.plan_basis_at, plan_basis_events=list(self.plan_basis_events),
                previous_holds=dict(self.previous_holds), previous_overrides=dict(self.previous_overrides),
                _nets=self._nets,
            )

    def snapshot(self) -> bytes:
        """Serialised scenario state (used to prove a what-if changes nothing)."""
        import pickle
        with self._lock:
            return pickle.dumps((self.timetable, self.events, sorted(self.holds.items()),
                                 sorted(self.route_overrides.items()), self.applied_recommendation,
                                 self.plan_basis_at, self.plan_basis_events,
                                 sorted(self.previous_holds.items()), sorted(self.previous_overrides.items()),
                                 sorted((k, v.decision) for k, v in self.recommendations.items()),
                                 self.decision_log))

    # ---- recommendations -----------------------------------------------------------
    def add_recommendation(self, at: int, strategy: str, holds: dict, route_overrides: dict,
                           payload: dict, known_event_ids: list[str] | None = None) -> Recommendation:
        with self._lock:
            rec = Recommendation(f"R{len(self.recommendations) + 1}", at, strategy, dict(holds),
                                 dict(route_overrides), payload, known_event_ids=list(known_event_ids or []))
            self.recommendations[rec.rec_id] = rec
            return rec

    def decide(self, rec_id: str, decision: str) -> Recommendation:
        with self._lock:
            rec = self.recommendations.get(rec_id)
            if rec is None:
                raise KeyError(rec_id)
            if rec.decision is not None:
                raise ValueError(f"{rec_id} was already decided ({rec.decision})")
            rec.decision = decision
            replaces = self.applied_recommendation if decision == "accept" else None
            if decision == "accept":
                self.previous_holds, self.previous_overrides = dict(self.holds), dict(self.route_overrides)
                self.holds = dict(rec.holds)
                self.route_overrides = dict(rec.route_overrides)
                self.applied_recommendation = rec_id
                self.plan_basis_at = rec.at
                self.plan_basis_events = list(rec.known_event_ids)
            entry = {"recommendation_id": rec_id, "decision": decision, "strategy": rec.strategy,
                     "at": rec.at, "replaces": replaces,
                     "logged_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.decision_log.append(entry)
            log.info("recommendation %s (%s) %sed", rec_id, rec.strategy, decision)
            return rec


_store = ScenarioStore()


def get_store() -> ScenarioStore:
    """FastAPI dependency; tests override it with a fresh store."""
    return _store
