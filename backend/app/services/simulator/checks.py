"""Safety checks on a simulated timeline.

Used by the tests to prove the simulator never breaks section capacity,
headway or track closures. Phase 3's conflict detector will build on the
same interval logic, applied to *planned* times instead of simulated ones.
"""
from __future__ import annotations

from app.services.network import RailNetwork, format_time
from app.services.simulator.engine import Disruption, SimResult


def find_violations(net: RailNetwork, result: SimResult,
                    disruptions: list[Disruption] | None = None) -> list[str]:
    problems: list[str] = []

    by_section: dict[str, list] = {}
    for occ in result.occupancies:
        by_section.setdefault(occ.section_id, []).append(occ)

    for sid, occs in by_section.items():
        sec = net.sections[sid]
        # each train blocks its track from entry until exit + headway
        points = []
        for o in occs:
            points.append((o.entry, 1, o.train_id))
            points.append((o.exit + sec.min_headway_min, -1, o.train_id))
        points.sort(key=lambda p: (p[0], p[1]))      # releases before entries at the same minute
        inside = 0
        for time, change, train_id in points:
            inside += change
            if inside > sec.tracks:
                problems.append(f"{sid}: {inside} trains within capacity+headway at {format_time(time)} "
                                f"(limit {sec.tracks}, entering: {train_id})")

        for o in occs:
            if o.exit - o.entry < sec.min_run_min:
                problems.append(f"{o.train_id} ran {sid} faster than the minimum running time")

    for d in disruptions or []:
        if d.event_type != "TRACK_UNAVAILABLE":
            continue
        for o in by_section.get(d.location, []):
            if o.entry < d.end and o.exit > d.start:
                problems.append(f"{o.train_id} used closed section {d.location}")

    for c in result.calls:
        if c.dep is not None and c.sched_dep is not None and c.dep < c.sched_dep:
            problems.append(f"{c.train_id} left {c.station} before its scheduled time")

    return problems
