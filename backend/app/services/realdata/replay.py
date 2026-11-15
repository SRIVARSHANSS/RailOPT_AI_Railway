"""REAL recorded day replay, DG -> MDU (Step 3).

A replay day is built from the recorded running times of every train whose DG date is `date`
(minutes after that date's midnight; may run past 24:00):

* `timetable` - the real timetable of those trains (ESTIMATED passing times included).
* `movement`  - the recorded movement as a network whose "schedule" IS what happened: recorded
  times at recorded stations, INTERPOLATED elsewhere. Simulating it with no events reproduces
  the recording exactly (tests check this), so the same simulator, conflict detector and
  optimizer work on top of it.
* `forecast(at)` - what a controller knows at `at`: the movement up to `at`, then the timetable
  with each train's current delay carried forward. Detection and re-planning use this (no
  knowledge of later recorded delays).

Interpolation (ASSUMPTIONS.md 67-68): a station a train did not record gets the scheduled time
plus the delay interpolated on km between its recorded neighbours (carried after the last). Where
two interpolated paths would cross inside a single-track section (an overtake the recording
does not locate), the overtaken train waits at the last station with a loop before the crossing
until the other train has cleared the next block; where a train would enter a block before the
leader cleared it, it waits at the block entrance (or the leader runs that block faster). Both
keep every recorded time and are marked INTERPOLATED. Pairs that cannot be repaired that way are
listed as unresolved.

Data label REAL; anything simulated on top is "HYPOTHETICAL on a real recorded day".
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date as Date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.services.network.model import (REAL_DATA_DIR, RailNetwork, StopTime, Train, build_network,
                                        load_network)
from app.services.realdata import corridor as C
from app.services.simulator import SimResult, find_violations, simulate
from app.services.simulator.engine import Occupancy, StationCall

REAL_LABEL = "REAL"
HYPOTHETICAL_LABEL = "HYPOTHETICAL on a real recorded day"
SOURCE = "RSTGCN Sept 2024 (CC BY-SA 4.0)"
REPAIR_ROUNDS = 50


@dataclass
class ReplayDay:
    date: str
    weekday: str
    timetable: RailNetwork
    movement: RailNetwork
    recorded: SimResult
    interpolated: dict[tuple[str, str], bool]          # (train_id, station) -> time interpolated
    placed: list[dict] = field(default_factory=list)   # waits placed by the repair (overtakes, spacing)
    unresolved: list[str] = field(default_factory=list)
    recorded_overtakes: list[dict] = field(default_factory=list)
    flagged_mdu: list[str] = field(default_factory=list)
    window: tuple[int, int] = (0, 1440)
    unreliable: list[dict] = field(default_factory=list)   # recorded times not used (implausible)
    upstream: dict[str, float] = field(default_factory=dict)   # last recorded pre-DG departure delay
    timetable_estimated: set[tuple[str, str]] = field(default_factory=set)   # ESTIMATED timetable cells

    @property
    def estimated(self) -> set[tuple[str, str]]:
        """(train, station) whose time is not firm: interpolated movement or ESTIMATED timetable."""
        return {k for k, v in self.interpolated.items() if v} | self.timetable_estimated

    @property
    def header(self) -> str:
        return f"REAL RECORDED MOVEMENTS - {self.date} - {SOURCE}"


# ---------------------------------------------------------------------------------------- data
@lru_cache(maxsize=1)
def _tables(real_dir: str = str(REAL_DATA_DIR)):
    d = Path(real_dir)
    sched = pd.read_csv(d / "schedule.csv")
    est = set(zip(sched[sched.time_source == "ESTIMATED"].train_id, sched[sched.time_source == "ESTIMATED"].station_code))
    return (pd.read_csv(d / "records.csv"), pd.read_csv(d / "runs.csv"),
            load_network(d, timetable="dg_mdu"), est)


def available_dates(real_dir: Path = REAL_DATA_DIR) -> list[str]:
    _recs, runs, _net, _est = _tables(str(real_dir))
    return sorted(set(runs.dg_date))


def _sub_network(full: RailNetwork, trains: dict[str, Train], schedules: dict[str, list[StopTime]]) -> RailNetwork:
    return build_network(full.stations, full.sections, trains, schedules)


# ---------------------------------------------------------------------------------------- build
def build_day(date: str, real_dir: Path = REAL_DATA_DIR) -> ReplayDay:
    recs, runs, full, tt_est = _tables(str(real_dir))
    day = recs[recs.dg_date == date]
    if day.empty:
        raise ValueError(f"no recorded runs on {date}; available: {available_dates(real_dir)[0]} .. "
                         f"{available_dates(real_dir)[-1]}")
    km = {c: s.km_from_start for c, s in full.stations.items()}
    r = runs[runs.dg_date == date]
    flagged = {f"R{t}" for t in r[(r.mdu_arr_delay == 0) & (r.dg_dep_delay >= 10)].train_no}

    trains, tt_sched, points, recorded_at, unreliable = {}, {}, {}, {}, []
    for t, g in day.groupby("train_no"):
        tid = f"R{t}"
        trains[tid] = full.trains[tid]
        tt_sched[tid] = full.schedules[tid]
        sched = {s.station: s for s in full.schedules[tid]}
        g = g.set_index("station_code")
        anchors = {s: (int(g.loc[s, "act_arr_min"]), int(g.loc[s, "act_dep_min"])) for s in g.index}
        if tid in flagged:
            anchors.pop("MDU", None)                 # MDU time suspected filled with the schedule
        dropped = _drop_implausible(full, anchors)
        unreliable += [{"train_id": tid, "station": s, "reason": "faster than the assumed minimum running time "
                        "from the previous recorded station"} for s in dropped]
        recorded_at[tid] = set(anchors)
        pts = {}
        known = [s for s in C.ORDER if s in anchors]
        for s in C.ORDER:
            if s in anchors:
                pts[s] = list(anchors[s])
                continue
            prev = [k for k in known if C.ORDER.index(k) < C.ORDER.index(s)]
            nxt = [k for k in known if C.ORDER.index(k) > C.ORDER.index(s)]
            sa = sched[s].sched_arr if sched[s].sched_arr is not None else sched[s].sched_dep
            sd = sched[s].sched_dep if sched[s].sched_dep is not None else sched[s].sched_arr
            if prev and nxt:
                a, b = prev[-1], nxt[0]
                da = anchors[a][1] - sched[a].sched_dep
                db = anchors[b][0] - sched[b].sched_arr
                d = da + (db - da) * (km[s] - km[a]) / (km[b] - km[a])
            elif prev:
                d = anchors[prev[-1]][1] - sched[prev[-1]].sched_dep
            else:
                d = anchors[nxt[0]][0] - sched[nxt[0]].sched_arr
            pts[s] = [round(sa + d), round(sd + d)]
        for s in C.ORDER:                             # keep times monotonic after rounding
            i = C.ORDER.index(s)
            if i:
                pts[s][0] = max(pts[s][0], pts[C.ORDER[i - 1]][1] + 1)
            pts[s][1] = max(pts[s][1], pts[s][0])
        points[tid] = pts

    placed, unresolved = _repair(full, points, recorded_at)
    interpolated = {(tid, s): s not in recorded_at[tid] or any(p["train_id"] == tid and s in p["stations"] for p in placed)
                    for tid in points for s in C.ORDER}

    mv_sched = {tid: [StopTime(s, k + 1, None if k == 0 else pts[s][0],
                               None if s == "MDU" else pts[s][1]) for k, s in enumerate(C.ORDER)]
                for tid, pts in points.items()}
    movement = _sub_network(full, trains, mv_sched)
    # the timetable's ESTIMATED passing times can cross inside a block too (e.g. the planned
    # 22627 / 16343 overtake): repair them the same way, keeping every listed (DATASET) time
    tt_pts = {tid: {s.station: [s.sched_arr if s.sched_arr is not None else s.sched_dep,
                                s.sched_dep if s.sched_dep is not None else s.sched_arr] for s in stops}
              for tid, stops in tt_sched.items()}
    _repair(full, tt_pts, {tid: {s for s in C.ORDER if (tid, s) not in tt_est} for tid in tt_pts})
    tt_sched = {tid: [StopTime(s.station, s.seq, None if s.sched_arr is None else tt_pts[tid][s.station][0],
                               None if s.sched_dep is None else tt_pts[tid][s.station][1]) for s in stops]
                for tid, stops in tt_sched.items()}
    timetable = _sub_network(full, trains, tt_sched)
    recorded = SimResult()
    for tid, pts in points.items():
        for k, s in enumerate(C.ORDER):
            recorded.calls.append(StationCall(tid, s, mv_sched[tid][k].sched_arr, mv_sched[tid][k].sched_dep,
                                              None if k == 0 else pts[s][0], None if s == "MDU" else pts[s][1]))
        for a, b in zip(C.ORDER, C.ORDER[1:]):
            recorded.occupancies.append(Occupancy(tid, f"S_{a}_{b}", pts[a][1], pts[a][1], pts[b][0], 0))
    recorded.occupancies.sort(key=lambda o: (o.entry, o.section_id))

    start = min(p["DG"][1] for p in points.values()) - 15
    end = max(p["MDU"][0] for p in points.values()) + 15
    wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][Date.fromisoformat(date).weekday()]
    return ReplayDay(date, wd, timetable, movement, recorded, interpolated, placed, unresolved,
                     _recorded_overtakes(points, recorded_at), sorted(flagged & set(points)),
                     (max(0, start - start % 5), end + (-end) % 5), unreliable,
                     {f"R{t}": float(u) for t, u in zip(r.train_no, r.upstream_dep_delay.fillna(0))},
                     {k for k in tt_est if k[0] in points})


def _drop_implausible(net, anchors: dict) -> list[str]:
    """Recorded times implying a run faster than the ASSUMED minimum running time between two
    recorded stations are treated as unreliable (the later one is dropped and interpolated)."""
    dropped = []
    while True:
        known = [s for s in C.ORDER if s in anchors]
        bad = None
        for a, b in zip(known, known[1:]):
            need = sum(net.sections[f"S_{x}_{y}"].min_run_min
                       for x, y in zip(C.ORDER[C.ORDER.index(a):C.ORDER.index(b)],
                                       C.ORDER[C.ORDER.index(a) + 1:C.ORDER.index(b) + 1]))
            if anchors[b][0] - anchors[a][1] < need:
                bad = b
                break
        if bad is None:
            return dropped
        anchors.pop(bad)
        dropped.append(bad)


def _recorded_overtakes(points, recorded_at) -> list[dict]:
    """Order changes between DG departure and MDU arrival, both recorded (where exactly is not recorded)."""
    out = []
    ids = [t for t in points if {"DG", "MDU"} <= recorded_at[t]]
    for a in ids:
        for b in ids:
            if points[a]["DG"][1] < points[b]["DG"][1] and points[b]["MDU"][0] < points[a]["MDU"][0]:
                out.append({"overtaking": b, "overtaken": a,
                            "dg_departures": [points[a]["DG"][1], points[b]["DG"][1]],
                            "mdu_arrivals": [points[a]["MDU"][0], points[b]["MDU"][0]]})
    return out


# ---------------------------------------------------------------------------------------- repair
def _respace(net, pts, rec, tid, start_station, start_dep) -> dict | None:
    """Train leaves `start_station` at `start_dep`; stations up to its next recorded one are
    re-timed linearly on km (passing). None if a section would be faster than its minimum."""
    i0 = C.ORDER.index(start_station)
    nxt = next((s for s in C.ORDER[i0 + 1:] if s in rec), None)
    end_station = nxt or "MDU"
    end_arr = pts[end_station][0] if nxt else max(pts["MDU"][0], 0)
    km = {s: net.stations[s].km_from_start for s in C.ORDER}
    new = {s: list(v) for s, v in pts.items()}
    new[start_station][1] = start_dep
    seg = C.ORDER[i0:C.ORDER.index(end_station) + 1]
    if not nxt:                                       # no anchor ahead: keep the old pace, shifted
        shift = start_dep - pts[start_station][1]
        for s in seg[1:]:
            new[s] = [pts[s][0] + shift, pts[s][1] + shift]
    else:
        span = end_arr - start_dep
        for s in seg[1:-1]:
            x = round(start_dep + span * (km[s] - km[start_station]) / (km[end_station] - km[start_station]))
            new[s] = [x, x]
    for a, b in zip(seg, seg[1:]):
        if new[b][0] - new[a][1] < net.sections[f"S_{a}_{b}"].min_run_min:
            return None
    return new


def _repair(net, points, recorded_at) -> tuple[list[dict], list[str]]:
    placed, unresolved = [], []
    loops = {c: s.loops for c, s in net.stations.items()}
    tried = set()
    for _ in range(REPAIR_ROUNDS):
        clash = None
        for a, b in zip(C.ORDER, C.ORDER[1:]):
            trips = sorted(((p[a][1], p[b][0], t) for t, p in points.items()), key=lambda x: (x[0], x[2]))
            for (ea, xa, ta), (eb, xb, tb) in zip(trips, trips[1:]):
                if eb < xa and (ta, tb, a) not in tried:
                    clash = (a, b, ta, tb, xb < xa)
                    break
            if clash:
                break
        if clash is None:
            break
        a, b, ta, tb, crossing = clash
        tried.add((ta, tb, a))
        A, B = points[ta], points[tb]
        fixed = None
        if crossing:
            # tb overtakes ta inside a->b: ta waits at the last loop station at or before a
            ia = C.ORDER.index(a)
            last_rec = max((C.ORDER.index(s) for s in recorded_at[ta] if C.ORDER.index(s) <= ia), default=0)
            for x in reversed(C.ORDER[last_rec:ia + 1]):
                if not loops[x] or x in recorded_at[ta] or x == "DG":
                    continue
                nx = C.ORDER[C.ORDER.index(x) + 1]
                if B[x][0] < A[x][0]:
                    continue
                new = _respace(net, A, recorded_at[ta], ta, x, max(A[x][1], B[nx][0]))
                if new:
                    points[ta] = new
                    fixed = {"train_id": ta, "kind": "overtaken", "by": tb, "station": x,
                             "wait_min": new[x][1] - new[x][0],
                             "stations": [s for s in C.ORDER if new[s] != A[s]]}
                    break
        else:
            # tb entered a->b before ta cleared it: tb waits at a, else ta runs a->b faster
            if a not in recorded_at[tb]:
                new = _respace(net, B, recorded_at[tb], tb, a, A[b][0])
                if new:
                    points[tb] = new
                    fixed = {"train_id": tb, "kind": "spacing", "behind": ta, "station": a,
                             "wait_min": new[a][1] - B[a][1], "stations": [s for s in C.ORDER if new[s] != B[s]]}
            if fixed is None and b not in recorded_at[ta]:
                run = max(net.sections[f"S_{a}_{b}"].min_run_min, B[a][1] - A[a][1])
                if A[a][1] + run <= B[a][1]:
                    new = {s: list(v) for s, v in A.items()}
                    new[b] = [A[a][1] + run, A[a][1] + run + (A[b][1] - A[b][0])]
                    rest = _respace(net, new, recorded_at[ta], ta, b, new[b][1])
                    if rest:
                        points[ta] = rest
                        fixed = {"train_id": ta, "kind": "faster", "ahead_of": tb, "station": b,
                                 "wait_min": 0, "stations": [s for s in C.ORDER if rest[s] != A[s]]}
        if fixed:
            placed.append(fixed)
            tried.clear()
        else:
            unresolved.append(f"{tb} would enter S_{a}_{b} before {ta} cleared it (interpolated times)")
    return placed, unresolved


# ---------------------------------------------------------------------------------------- knowledge
def forecast(day: ReplayDay, at: int, actual: SimResult | None = None) -> RailNetwork:
    """What a controller knows at `at`: the movement (recorded, or the hypothetical `actual`) up
    to `at`; after it, the timetable with the train's current delay carried forward."""
    res = actual or day.recorded
    sched = {}
    for tid, stops in day.timetable.schedules.items():
        calls = {c.station: c for c in res.calls if c.train_id == tid}
        delay = round(day.upstream.get(tid, 0))      # before DG: the last recorded upstream delay (ASSUMED known)
        out = []
        for k, s in enumerate(stops):
            c = calls[s.station]
            arr = None if k == 0 else (c.arr if c.arr is not None and c.arr <= at else s.sched_arr + delay)
            if k and c.arr is not None and c.arr <= at:
                delay = c.arr - s.sched_arr
            if s.station == "MDU":
                dep = None
            elif c.dep is not None and c.dep <= at:
                dep = c.dep
                delay = c.dep - s.sched_dep
            else:
                dep = max(s.sched_dep + delay, arr if arr is not None else s.sched_dep + delay)
            out.append(StopTime(s.station, s.seq, arr, dep))
        # known departure from DG before `at`; otherwise the recorded DG departure is the
        # boundary condition only once it has happened
        sched[tid] = out
    return _with_history(_sub_network(day.timetable, day.timetable.trains, sched), res, at)


DEMO_DAY = "2024-09-12"      # Thursday, 22 trains, replays exactly, recorded 22627 overtakes 16343


@lru_cache(maxsize=1)
def day_checks() -> list[dict]:
    return [check_day(get_day(d)) for d in available_dates()]


@lru_cache(maxsize=40)
def get_day(date: str) -> ReplayDay:
    """Cached build (the API uses one day at a time; the data is read-only)."""
    return build_day(date)


def _with_history(net: RailNetwork, result: SimResult, before: int) -> RailNetwork:
    """Copy of `net` whose trips entered before `before` are fixed as in `result` (history)."""
    out = _sub_network(net, net.trains, net.schedules)
    out.frozen = {(o.train_id, o.section_id): (o.entry, o.exit - o.stopped_min)
                  for o in result.occupancies if o.entry < before}
    out.frozen_before = before
    return out


def frozen_movement(day: ReplayDay, before: int) -> RailNetwork:
    """The recorded movement with everything entered before `before` fixed as recorded."""
    return _with_history(day.movement, day.recorded, before)


def with_headway(net: RailNetwork, headway: int) -> RailNetwork:
    """Same network with every section's minimum headway set to `headway` (sensitivity runs)."""
    sections = {sid: dataclasses.replace(s, min_headway_min=headway) for sid, s in net.sections.items()}
    out = build_network(net.stations, sections, net.trains, net.schedules)
    out.frozen, out.frozen_before = dict(net.frozen), net.frozen_before
    return out


def planned_rows(day: ReplayDay) -> list[dict]:
    """The real timetable as chart rows, straight from the schedule (not simulated)."""
    from app.services.network import format_time
    rows = []
    for tid, stops in day.timetable.schedules.items():
        for a, b in zip(stops, stops[1:]):
            sec = day.timetable.sections[f"S_{a.station}_{b.station}"]
            rows.append({"train_id": tid, "section_id": sec.section_id, "from_station": a.station,
                         "to_station": b.station, "from_km": day.timetable.stations[a.station].km_from_start,
                         "to_km": day.timetable.stations[b.station].km_from_start,
                         "entry_min": a.sched_dep, "exit_min": b.sched_arr, "entry": format_time(a.sched_dep),
                         "exit": format_time(b.sched_arr), "wait_min": 0, "stopped_min": 0, "stops": [],
                         "delay_min": 0, "alternate": False,
                         "interpolated": (tid, a.station) in day.timetable_estimated
                         or (tid, b.station) in day.timetable_estimated})
    return rows


def info(day: ReplayDay, divergence: int | None) -> dict:
    from app.services.network import format_time
    return {
        "date": day.date, "weekday": day.weekday, "header": day.header, "source": SOURCE,
        "window_start": day.window[0], "window_end": day.window[1], "trains": len(day.movement.trains),
        "divergence": None if divergence is None else format_time(divergence),
        "recorded_overtakes": [{**o, "dg_departures": [format_time(x) for x in o["dg_departures"]],
                                "mdu_arrivals": [format_time(x) for x in o["mdu_arrivals"]]}
                               for o in day.recorded_overtakes],
        "placed_waits": day.placed, "unreliable": day.unreliable, "unresolved": day.unresolved,
        "flagged_mdu": day.flagged_mdu,
        "notes": [
            "Trains move by their RECORDED times at recorded stations; elsewhere times are INTERPOLATED "
            "on km (where an overtake or a block wait had to be placed, at a loop station).",
            "With a hypothetical event or an accepted plan, movement before its start stays as recorded; "
            "after it, trains are simulated from the recorded movement (HYPOTHETICAL on a real recorded day).",
            "Detection and re-planning see what was known at the clock time: recorded movement so far, then "
            "the timetable with current delays carried forward.",
            "ASSUMED: priorities PREMIUM 1, SUPERFAST 2, EXPRESS 3 (objective weights 3/2/1); loops per "
            "station; minimum running time at 110 km/h. CALIBRATED: headway 0 min (one train per block section).",
        ],
    }


def check_day(day: ReplayDay) -> dict:
    sim = simulate(day.movement)
    exact = all((o.entry, o.exit) == (r.entry, r.exit) for o, r in zip(
        sorted(sim.occupancies, key=lambda o: (o.train_id, o.entry)),
        sorted(day.recorded.occupancies, key=lambda o: (o.train_id, o.entry))))
    return {"date": day.date, "weekday": day.weekday, "trains": len(day.movement.trains),
            "placed": len(day.placed), "unresolved": len(day.unresolved), "unreliable": len(day.unreliable),
            "violations": len(find_violations(day.movement, day.recorded)), "reproduced_exactly": exact,
            "recorded_overtakes": len(day.recorded_overtakes)}


if __name__ == "__main__":
    rows = [check_day(build_day(d)) for d in available_dates()]
    print(json.dumps(rows, indent=1))
