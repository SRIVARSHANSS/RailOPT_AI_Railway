"""Event-driven railway simulator (custom discrete-event loop).

How it works
------------
Each train follows its timetable station by station. When a train is ready
to leave a station it *requests* the next section. Requests are processed in
time order (ties broken by priority). A train may enter a section only when

* a track in the section is free, counting the minimum headway after the
  previous train on that track cleared it,
* the section is not blocked by a TRACK_UNAVAILABLE event during the trip,
* any controller hold given to the simulator has expired.

Otherwise it waits at the station signal. This is the "no re-planning,
first-come-first-served" behaviour, which is also the baseline the
optimizer will be compared against later.

Disruptions supported in Phase 1
--------------------------------
* STOPPAGE  - train stops inside a section for `duration_min`, starting at
  `start_time` (must happen while the train is in that section).
* DELAY     - train cannot leave station `location` before `start_time` +
  `duration_min` (an extra hold at that station).
* TRACK_UNAVAILABLE - section `location` cannot be used from `start_time`
  for `duration_min`.
* PLATFORM_UNAVAILABLE - recorded but not simulated yet (platform model is a
  later phase); listed in `SimResult.ignored_events`.

All results are SIMULATED. Nothing here is connected to real railway systems.
"""
from __future__ import annotations

import csv
import heapq
import random
from dataclasses import dataclass, field
from pathlib import Path

from app.services.network import RailNetwork, Section, StopTime, format_time, parse_time

EVENT_TYPES = {"STOPPAGE", "DELAY", "TRACK_UNAVAILABLE", "PLATFORM_UNAVAILABLE"}


@dataclass(frozen=True)
class Disruption:
    event_id: str
    event_type: str
    train_id: str | None
    location: str           # section_id or station code
    start: int              # minutes after midnight
    duration: int           # minutes
    # STOPPAGE only: minutes into the train's planned trip. Used only when the
    # simulator runs with an rng and variability moved the train away from
    # `start`: the stoppage is then applied at actual entry + offset_min.
    offset_min: int | None = None

    @property
    def end(self) -> int:
        return self.start + self.duration


@dataclass
class Occupancy:
    """One train's use of one section."""
    train_id: str
    section_id: str
    requested: int      # when the train was ready to enter
    entry: int          # when it actually entered
    exit: int           # when it cleared the section
    stopped_min: int = 0

    @property
    def wait(self) -> int:
        return self.entry - self.requested


@dataclass
class StationCall:
    train_id: str
    station: str
    sched_arr: int | None
    sched_dep: int | None
    arr: int | None = None
    dep: int | None = None

    @property
    def arr_delay(self) -> int | None:
        if self.arr is None or self.sched_arr is None:
            return None
        return self.arr - self.sched_arr

    @property
    def dep_delay(self) -> int | None:
        if self.dep is None or self.sched_dep is None:
            return None
        return self.dep - self.sched_dep


@dataclass
class SimResult:
    occupancies: list[Occupancy] = field(default_factory=list)
    calls: list[StationCall] = field(default_factory=list)
    applied_events: list[str] = field(default_factory=list)
    ignored_events: list[str] = field(default_factory=list)

    # ---- convenience lookups -------------------------------------------
    def occupancy(self, train_id: str, section_id: str) -> Occupancy:
        for occ in self.occupancies:
            if occ.train_id == train_id and occ.section_id == section_id:
                return occ
        raise KeyError(f"{train_id} did not use {section_id}")

    def call(self, train_id: str, station: str) -> StationCall:
        for c in self.calls:
            if c.train_id == train_id and c.station == station:
                return c
        raise KeyError(f"{train_id} does not call at {station}")

    def final_delay(self, train_id: str) -> int:
        """Arrival delay at the train's destination, in minutes."""
        last = [c for c in self.calls if c.train_id == train_id][-1]
        return last.arr_delay or 0

    # ---- metrics ---------------------------------------------------------
    def metrics(self) -> dict[str, float]:
        train_ids = sorted({c.train_id for c in self.calls})
        delays = [self.final_delay(t) for t in train_ids]
        arrivals = [[c for c in self.calls if c.train_id == t][-1].arr for t in train_ids]
        departures = [[c for c in self.calls if c.train_id == t][0].dep for t in train_ids]
        span_h = max(1, (max(arrivals) - min(departures))) / 60 if train_ids else 1
        return {
            "trains": len(train_ids),
            "total_delay_min": sum(delays),
            "avg_delay_min": round(sum(delays) / len(delays), 2) if delays else 0.0,
            "max_delay_min": max(delays) if delays else 0,
            "delayed_trains": sum(1 for d in delays if d > 0),
            "total_wait_min": sum(o.wait for o in self.occupancies),
            "throughput_trains_per_hour": round(len(train_ids) / span_h, 2),
        }


# ---------------------------------------------------------------------------
# Loading events
# ---------------------------------------------------------------------------
def load_events(path: str | Path) -> list[Disruption]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [
        Disruption(
            event_id=r["event_id"],
            event_type=r["event_type"].strip().upper(),
            train_id=(r.get("train_id") or "").strip() or None,
            location=r["location"].strip(),
            start=parse_time(r["start_time"]),
            duration=int(r["duration_min"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Random variability (assumed ranges, documented in docs/ASSUMPTIONS.md)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Variability:
    """How much slower than planned a train may run, drawn per section trip.

    run_slowdown_max: train type -> maximum fractional slowdown of the
        running time (0.05 = up to 5 % slower). Rounded to whole minutes, so
        a train is never faster than planned and never below min_run_min.
    dwell_overrun_max_min: at stations where the train has a timetabled stop,
        it may leave 0..N whole minutes later than the dwell rule allows.
        Trains passing a station without stopping get no overrun.
    """
    run_slowdown_max: tuple[tuple[str, float], ...] = (
        ("EXPRESS", 0.05), ("PASSENGER", 0.10), ("FREIGHT", 0.20))
    dwell_overrun_max_min: int = 3

    def extra_run_minutes(self, rng: random.Random, train_type: str, run: int) -> int:
        return round(run * rng.uniform(0.0, dict(self.run_slowdown_max)[train_type]))

    def dwell_overrun_minutes(self, rng: random.Random, stop: StopTime) -> int:
        dwell = (stop.sched_dep - stop.sched_arr) if stop.sched_arr is not None else 0
        return rng.randint(0, self.dwell_overrun_max_min) if dwell > 0 else 0

    def as_dict(self) -> dict:
        return {"run_slowdown_max_fraction": dict(self.run_slowdown_max),
                "dwell_overrun_max_min": self.dwell_overrun_max_min}


DEFAULT_VARIABILITY = Variability()


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def simulate(
    net: RailNetwork,
    disruptions: list[Disruption] | None = None,
    route_overrides: dict[tuple[str, str], str] | None = None,
    holds: dict[tuple[str, str], int] | None = None,
    rng: random.Random | None = None,
    variability: Variability | None = None,
) -> SimResult:
    """Run the corridor once and return every train's timeline.

    route_overrides: {(train_id, from_station): section_id} - e.g. send T202
        over S_BC_ALT instead of S_BC (used by the reroute strategy later).
    holds: {(train_id, section_id): earliest_entry_minute} - a controller
        hold (used by the hold / resequence strategies later).
    rng: if given, running times and dwells vary randomly (see Variability).
        rng=None keeps the simulator fully deterministic, exactly as before.
    variability: the random ranges; DEFAULT_VARIABILITY when rng is given.
    """
    if rng is not None and variability is None:
        variability = DEFAULT_VARIABILITY
    disruptions = list(disruptions or [])
    route_overrides = dict(route_overrides or {})
    holds = dict(holds or {})
    result = SimResult()
    validate_events(net, disruptions, result)

    # track_free_at[section_id] = list with one "free from" time per track
    track_free_at: dict[str, list[int]] = {
        sid: [-10**9] * sec.tracks for sid, sec in net.sections.items()
    }
    blocks: dict[str, list[tuple[int, int]]] = {}
    for d in disruptions:
        if d.event_type == "TRACK_UNAVAILABLE":
            blocks.setdefault(d.location, []).append((d.start, d.end))
            result.applied_events.append(f"{d.event_id}: {d.location} closed {format_time(d.start)}-{format_time(d.end)}")

    # station calls, prepared from the timetable
    calls: dict[str, list[StationCall]] = {}
    for train_id, stops in net.schedules.items():
        calls[train_id] = [StationCall(train_id, s.station, s.sched_arr, s.sched_dep) for s in stops]

    # every train starts by requesting its first section at its origin departure time
    queue: list[tuple[int, int, str, int]] = []   # (time, priority, train_id, stop_index)
    for train_id, stops in net.schedules.items():
        ready = _apply_station_delay(stops[0].sched_dep, train_id, stops[0].station, disruptions, result)
        heapq.heappush(queue, (ready, net.trains[train_id].priority, train_id, 0))

    while queue:
        ready, _prio, train_id, i = heapq.heappop(queue)
        stops = net.schedules[train_id]
        here, nxt = stops[i], stops[i + 1]
        sec = _choose_section(net, train_id, here.station, nxt.station, route_overrides)

        run = _running_time(net, sec, here, nxt)
        if rng is not None:
            run += variability.extra_run_minutes(rng, net.trains[train_id].train_type, run)
        entry, track = _earliest_entry(sec, ready, run, track_free_at[sec.section_id],
                                       blocks.get(sec.section_id, []),
                                       holds.get((train_id, sec.section_id)))
        stopped = _stoppage_minutes(train_id, sec, entry, entry + run, disruptions, result,
                                    shift_if_missed=rng is not None)
        exit_time = entry + run + stopped
        track_free_at[sec.section_id][track] = exit_time + sec.min_headway_min

        result.occupancies.append(Occupancy(train_id, sec.section_id, ready, entry, exit_time, stopped))
        calls[train_id][i].dep = entry
        calls[train_id][i + 1].arr = exit_time

        if i + 1 < len(stops) - 1:
            next_ready = next_departure(nxt, exit_time)
            if rng is not None:
                next_ready += variability.dwell_overrun_minutes(rng, nxt)
            next_ready = _apply_station_delay(next_ready, train_id, nxt.station, disruptions, result)
            heapq.heappush(queue, (next_ready, net.trains[train_id].priority, train_id, i + 1))

    for train_id in net.schedules:
        result.calls.extend(calls[train_id])
    result.occupancies.sort(key=lambda o: (o.entry, o.section_id))
    return result


# ---------------------------------------------------------------------------
# helpers (also used by the Phase 3 conflict detector's planner)
# ---------------------------------------------------------------------------
def validate_events(net: RailNetwork, disruptions: list[Disruption], result: SimResult) -> None:
    """Reject unknown event types and sections; note events not modelled yet."""
    for d in disruptions:
        if d.event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type {d.event_type}")
        if d.event_type == "PLATFORM_UNAVAILABLE":
            result.ignored_events.append(f"{d.event_id}: platform model not built yet")
        if d.event_type == "TRACK_UNAVAILABLE" and d.location not in net.sections:
            raise ValueError(f"{d.event_id}: unknown section {d.location}")


def next_departure(nxt: StopTime, arrival: int) -> int:
    """Dwell rule: keep the timetabled stop length, never leave before schedule."""
    dwell = (nxt.sched_dep - nxt.sched_arr) if nxt.sched_arr is not None else 0
    return max(nxt.sched_dep, arrival + dwell)


def _choose_section(net, train_id, a, b, overrides) -> Section:
    sid = overrides.get((train_id, a))
    if sid:
        sec = net.sections[sid]
        if (sec.from_station, sec.to_station) != (a, b):
            raise ValueError(f"{sid} does not run {a}->{b}")
        return sec
    return net.primary_section(a, b)


def _running_time(net, sec, here, nxt) -> int:
    """Timetabled running time on the planned section, never below the minimum.

    On an alternate section the train needs that section's own minimum time.
    """
    planned = net.primary_section(here.station, nxt.station)
    scheduled = nxt.sched_arr - here.sched_dep
    if sec.section_id == planned.section_id:
        return max(sec.min_run_min, scheduled)
    return max(sec.min_run_min, scheduled + (sec.min_run_min - planned.min_run_min))


def _earliest_entry(sec, ready, run, free_at, blocks, hold) -> tuple[int, int]:
    """Earliest time >= ready when a track is free and the trip avoids closures."""
    t = max(ready, hold if hold is not None else ready)
    while True:
        track = min(range(len(free_at)), key=lambda k: free_at[k])
        t = max(t, free_at[track])
        clash = next(((s, e) for s, e in blocks if t < e and t + run > s), None)
        if clash is None:
            return t, track
        t = clash[1]


def _stoppage_minutes(train_id, sec, entry, planned_exit, disruptions, result,
                      shift_if_missed: bool = False) -> int:
    """Minutes a train stands inside `sec` because of STOPPAGE events.

    Deterministic runs: the stoppage applies only if the train is inside at
    `start`. With variability (shift_if_missed) a stoppage that has an
    offset_min and misses the train is applied at actual entry + offset_min.
    """
    total = 0
    for d in disruptions:
        if d.event_type != "STOPPAGE" or d.train_id != train_id or d.location != sec.section_id:
            continue
        if entry <= d.start < planned_exit + total:
            total += d.duration
            result.applied_events.append(
                f"{d.event_id}: {train_id} stopped in {sec.section_id} at {format_time(d.start)} for {d.duration} min")
        elif shift_if_missed and d.offset_min is not None:
            at = entry + min(d.offset_min, planned_exit + total - entry - 1)
            total += d.duration
            result.applied_events.append(
                f"{d.event_id}: {train_id} not in {sec.section_id} at {format_time(d.start)} after variability; "
                f"stopped at {format_time(at)} (actual entry + {at - entry} min) for {d.duration} min")
        else:
            result.ignored_events.append(
                f"{d.event_id}: {train_id} was not inside {sec.section_id} at {format_time(d.start)}")
    return total


def _apply_station_delay(ready, train_id, station, disruptions, result) -> int:
    for d in disruptions:
        if d.event_type == "DELAY" and d.train_id == train_id and d.location == station:
            ready = max(ready, d.start + d.duration)
            result.applied_events.append(
                f"{d.event_id}: {train_id} held at {station} until {format_time(d.start + d.duration)}")
    return ready
