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


@dataclass
class ScenarioStore:
    timetable: str = "reference"
    events: list[Disruption] = field(default_factory=list)
    holds: dict[tuple[str, str], int] = field(default_factory=dict)
    route_overrides: dict[tuple[str, str], str] = field(default_factory=dict)
    applied_recommendation: str | None = None
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
            self.recommendations.clear()
            self.decision_log.clear()

    def add_event(self, event_type: str, train_id: str | None, location: str,
                  start: int, duration: int) -> Disruption:
        with self._lock:
            event = Disruption(f"E{len(self.events) + 1}", event_type, train_id, location, start, duration)
            self.events.append(event)
            return event

    def known_events(self, at: int) -> list[Disruption]:
        """Events the controller knows about at clock time `at`."""
        return [e for e in self.events if e.event_type in PLANNED_EVENT_TYPES or e.start <= at]

    def actual(self) -> SimResult:
        """What happens: every posted event, plus the accepted plan (holds / reroutes)."""
        return simulate(self.network(), self.events, route_overrides=self.route_overrides, holds=self.holds)

    # ---- recommendations -----------------------------------------------------------
    def add_recommendation(self, at: int, strategy: str, holds: dict, route_overrides: dict,
                           payload: dict) -> Recommendation:
        with self._lock:
            rec = Recommendation(f"R{len(self.recommendations) + 1}", at, strategy, dict(holds),
                                 dict(route_overrides), payload)
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
            if decision == "accept":
                self.holds = dict(rec.holds)
                self.route_overrides = dict(rec.route_overrides)
                self.applied_recommendation = rec_id
            entry = {"recommendation_id": rec_id, "decision": decision, "strategy": rec.strategy,
                     "at": rec.at, "logged_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.decision_log.append(entry)
            log.info("recommendation %s (%s) %sed", rec_id, rec.strategy, decision)
            return rec


_store = ScenarioStore()


def get_store() -> ScenarioStore:
    """FastAPI dependency; tests override it with a fresh store."""
    return _store
