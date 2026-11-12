"""Safety checks on a timeline of section occupancies.

The interval logic here is shared:

* `find_violations` uses it on the simulator's *actual* timeline, to prove
  the simulator never breaks section capacity, headway or track closures.
* the Phase 3 conflict detector (app/services/conflicts) uses the same
  functions on *planned* times, to flag conflicts before they happen.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.services.network import RailNetwork, format_time
from app.services.simulator.engine import Disruption, Occupancy, SimResult


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """True if the half-open intervals [a_start, a_end) and [b_start, b_end) overlap."""
    return a_start < b_end and a_end > b_start


@dataclass(frozen=True)
class TrackClash:
    """`later` wanted a track while `earlier` still held it (exit + headway)."""
    earlier: Occupancy
    later: Occupancy
    free_from: int      # earliest minute `later` could have entered that track


def track_clashes(occupancies: Iterable[Occupancy], tracks: int, headway: int,
                  priority: Callable[[str], int] | None = None) -> list[TrackClash]:
    """Give each train a track in entry order and report every clash.

    A train blocks its track from entry until exit + headway. Each train
    takes the track that becomes free first; if even that track is still
    blocked at the train's entry time, it is a clash. The later train then
    becomes that track's holder with its own times (nobody is made to wait
    here; that is the simulator's job). Ties on entry go to higher priority
    (lower number).
    """
    def order(o: Occupancy):
        return (o.entry, priority(o.train_id) if priority else 0, o.train_id)

    holders: list[Occupancy | None] = [None] * tracks

    def free_at(k: int) -> int:
        h = holders[k]
        return -10**9 if h is None else h.exit + headway

    clashes: list[TrackClash] = []
    for occ in sorted(occupancies, key=order):
        k = min(range(tracks), key=free_at)
        if free_at(k) > occ.entry:
            clashes.append(TrackClash(holders[k], occ, free_at(k)))
        holders[k] = occ
    return clashes


def group_by_section(occupancies: Iterable[Occupancy]) -> dict[str, list[Occupancy]]:
    by_section: dict[str, list[Occupancy]] = {}
    for occ in occupancies:
        by_section.setdefault(occ.section_id, []).append(occ)
    return by_section


def find_violations(net: RailNetwork, result: SimResult,
                    disruptions: list[Disruption] | None = None) -> list[str]:
    problems: list[str] = []
    by_section = group_by_section(result.occupancies)

    for sid, occs in by_section.items():
        sec = net.sections[sid]
        for c in track_clashes(occs, sec.tracks, sec.min_headway_min):
            problems.append(f"{sid}: {c.later.train_id} entered at {format_time(c.later.entry)} but "
                            f"{c.earlier.train_id} held the track until {format_time(c.free_from)} "
                            f"(capacity {sec.tracks}, headway {sec.min_headway_min} min)")

        for o in occs:
            if o.exit - o.entry < sec.min_run_min:
                problems.append(f"{o.train_id} ran {sid} faster than the minimum running time")

    for d in disruptions or []:
        if d.event_type != "TRACK_UNAVAILABLE":
            continue
        for o in by_section.get(d.location, []):
            if overlaps(o.entry, o.exit, d.start, d.end):
                problems.append(f"{o.train_id} used closed section {d.location}")

    for c in result.calls:
        if c.dep is not None and c.sched_dep is not None and c.dep < c.sched_dep:
            problems.append(f"{c.train_id} left {c.station} before its scheduled time")

    return problems
