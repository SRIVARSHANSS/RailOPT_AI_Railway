"""Rule-based conflict detector (Phase 3).

Predicts conflicts BEFORE they happen, from planned times:

1. `project_plan` projects every train's planned occupancy of each section,
   assuming each train keeps its timetable and its own known disruptions are
   applied (a stoppage makes that train leave the section later, a delay
   holds it at a station, and its own lateness carries on down its route),
   but WITHOUT making any train wait for another. The simulator would
   resolve the clashes by waiting; the plan deliberately leaves them in.
2. `detect_conflicts` checks that plan for capacity, headway and closure
   clashes, using the same interval logic as the simulator's safety checks.
3. `estimate_cascade` runs the existing simulator (no re-planning, first
   come first served) to show the knock-on delay on the trains that follow.

All results are SIMULATED on the sample corridor. Nothing here is connected
to real railway systems or controls trains or signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.network import RailNetwork
from app.services.simulator.checks import group_by_section, overlaps, track_clashes
from app.services.simulator.engine import (
    Disruption,
    Occupancy,
    SimResult,
    _apply_station_delay,
    _running_time,
    _stoppage_minutes,
    next_departure,
    simulate,
    validate_events,
)

SIMULATED_LABEL = "SIMULATED - sample corridor, not real railway data"

OVERLAP = "OVERLAP"     # later train would enter while the earlier one is still inside
HEADWAY = "HEADWAY"     # earlier train has cleared, but the minimum headway is not met
CLOSURE = "CLOSURE"     # planned trip overlaps a TRACK_UNAVAILABLE window

CRITICAL_WITHIN_MIN = 10   # time_to_conflict <= 10 min -> CRITICAL, else WARNING


@dataclass
class Plan:
    """Planned section occupancies as seen at `state_time` (minutes after midnight)."""
    state_time: int
    trips: list[Occupancy]
    disruptions: list[Disruption]
    applied_events: list[str] = field(default_factory=list)
    ignored_events: list[str] = field(default_factory=list)
    label: str = SIMULATED_LABEL

    def trip(self, train_id: str, section_id: str) -> Occupancy:
        for t in self.trips:
            if t.train_id == train_id and t.section_id == section_id:
                return t
        raise KeyError(f"{train_id} does not plan to use {section_id}")


@dataclass
class Conflict:
    conflict_id: str
    section_id: str
    trains: tuple[str | None, str]   # (earlier, later); earlier is None for a CLOSURE
    window_start: int                # when the later train planned to enter
    window_end: int                  # earliest minute it could safely enter
    conflict_type: str               # OVERLAP | HEADWAY | CLOSURE
    minutes_short: int               # how long the later train must wait
    time_to_conflict: int            # minutes from state_time to window_start
    severity: str                    # CRITICAL | WARNING
    event_id: str | None = None      # the TRACK_UNAVAILABLE event, for CLOSURE

    @property
    def earlier(self) -> str | None:
        return self.trains[0]

    @property
    def later(self) -> str:
        return self.trains[1]


@dataclass(frozen=True)
class TrainImpact:
    train_id: str
    wait_at_section_min: int   # simulated wait before entering the conflict section
    final_delay_min: int       # simulated arrival delay at destination


@dataclass
class CascadeReport:
    conflict_id: str
    section_id: str
    source_train: str           # the train whose disruption causes the conflict
    impacts: list[TrainImpact]  # every train, in simulated order through the section
    total_delay_min: int
    label: str = SIMULATED_LABEL

    @property
    def knock_on(self) -> list[TrainImpact]:
        """Every train after the source train."""
        return [i for i in self.impacts if i.train_id != self.source_train]

    def impact(self, train_id: str) -> TrainImpact:
        return next(i for i in self.impacts if i.train_id == train_id)


# ---------------------------------------------------------------------------
# 1. planned occupancies
# ---------------------------------------------------------------------------
def project_plan(net: RailNetwork, state_time: int,
                 disruptions: list[Disruption] | None = None) -> Plan:
    disruptions = list(disruptions or [])
    log = SimResult()                     # collects applied / ignored event notes
    validate_events(net, disruptions, log)

    trips: list[Occupancy] = []
    for train_id, stops in net.schedules.items():
        ready = _apply_station_delay(stops[0].sched_dep, train_id, stops[0].station, disruptions, log)
        for i in range(len(stops) - 1):
            here, nxt = stops[i], stops[i + 1]
            sec = net.primary_section(here.station, nxt.station)
            run = _running_time(net, sec, here, nxt)
            stopped = _stoppage_minutes(train_id, sec, ready, ready + run, disruptions, log)
            exit_time = ready + run + stopped
            trips.append(Occupancy(train_id, sec.section_id, ready, ready, exit_time, stopped))
            if i + 1 < len(stops) - 1:
                ready = next_departure(nxt, exit_time)
                ready = _apply_station_delay(ready, train_id, nxt.station, disruptions, log)

    trips.sort(key=lambda o: (o.entry, o.section_id, o.train_id))
    return Plan(state_time, trips, disruptions, log.applied_events, log.ignored_events)


# ---------------------------------------------------------------------------
# 2. conflicts
# ---------------------------------------------------------------------------
def detect_conflicts(net: RailNetwork, plan: Plan) -> list[Conflict]:
    found: list[dict] = []
    by_section = group_by_section(plan.trips)

    for sid, trips in by_section.items():
        sec = net.sections[sid]
        clashes = track_clashes(trips, sec.tracks, sec.min_headway_min,
                                priority=lambda t: net.trains[t].priority)
        for c in clashes:
            ctype = OVERLAP if c.later.entry < c.earlier.exit else HEADWAY
            found.append(dict(section_id=sid, trains=(c.earlier.train_id, c.later.train_id),
                              window_start=c.later.entry, window_end=c.free_from, conflict_type=ctype))

    for d in plan.disruptions:
        if d.event_type != "TRACK_UNAVAILABLE":
            continue
        for t in by_section.get(d.location, []):
            if overlaps(t.entry, t.exit, d.start, d.end):
                found.append(dict(section_id=d.location, trains=(None, t.train_id),
                                  window_start=t.entry, window_end=d.end,
                                  conflict_type=CLOSURE, event_id=d.event_id))

    # conflicts already over at state_time are history, not predictions
    found = [f for f in found if f["window_end"] > plan.state_time]
    found.sort(key=lambda f: (f["window_start"], f["section_id"], f["trains"][1]))

    conflicts = []
    for n, f in enumerate(found, start=1):
        time_to = f["window_start"] - plan.state_time
        conflicts.append(Conflict(
            conflict_id=f"C{n}",
            minutes_short=f["window_end"] - f["window_start"],
            time_to_conflict=time_to,
            severity="CRITICAL" if time_to <= CRITICAL_WITHIN_MIN else "WARNING",
            **f,
        ))
    return conflicts


# ---------------------------------------------------------------------------
# 3. knock-on effects
# ---------------------------------------------------------------------------
def estimate_cascade(net: RailNetwork, disruptions: list[Disruption] | None,
                     conflict: Conflict) -> CascadeReport:
    """Simulate with no re-planning and report every train's knock-on delay."""
    result = simulate(net, disruptions)
    source = conflict.earlier or conflict.later

    on_section = [o for o in result.occupancies if o.section_id == conflict.section_id]
    order = [o.train_id for o in sorted(on_section, key=lambda o: o.entry)]
    order += sorted(t for t in net.schedules if t not in order)
    waits = {o.train_id: o.wait for o in on_section}

    impacts = [TrainImpact(t, waits.get(t, 0), result.final_delay(t)) for t in order]
    return CascadeReport(conflict.conflict_id, conflict.section_id, source, impacts,
                         sum(i.final_delay_min for i in impacts))
