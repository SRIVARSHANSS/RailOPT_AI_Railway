"""Views of a scenario at a clock time: train states, conflicts + ML, plans.

Plain Python (no FastAPI) so it can be tested directly. All SIMULATED.
"""
from __future__ import annotations

from app.services import explainer
from app.services.conflicts import detect_conflicts, project_plan
from app.services.network import RailNetwork, format_time
from app.services.optimizer import compare
from app.services.optimizer.solver import STRATEGIES
from app.services.simulator import Disruption, SimResult, simulate

STRATEGY_ORDER = {s.name: k for k, s in enumerate(STRATEGIES)}
NO_ALTERNATE_REASON = ("No alternate line on this corridor (one track per direction between Dindigul and "
                       "Madurai), so rerouting is not possible; only HOLD and RESEQUENCE are offered.")


def available_strategies(net: RailNetwork) -> tuple[list[str] | None, list[dict]]:
    """REROUTE / COMBINED only where a standby (alternate) section exists."""
    if any(s.status == "standby" for s in net.sections.values()):
        return None, []
    return ["HOLD", "RESEQUENCE"], [{"name": n, "reason": NO_ALTERNATE_REASON} for n in ("REROUTE", "COMBINED")]


# ---------------------------------------------------------------------------
# train states
# ---------------------------------------------------------------------------
def train_states(net: RailNetwork, result: SimResult, at: int,
                 disruptions: list[Disruption] | None = None,
                 estimated: set[tuple[str, str]] | None = None) -> list[dict]:
    """Where every train is at `at` in a simulated timeline, and how late it is.

    progress (in a section) is the share of the RUNNING time covered: minutes spent
    standing in a STOPPAGE do not move the train. `stopped` is true during a stoppage.

    current_delay_min:
      in a section        max(departure delay, at - scheduled arrival at the next station)
      at station / signal max(arrival delay there, at - scheduled departure)
      arrived             arrival delay at destination
    """
    states = []
    for train_id, stops in net.schedules.items():
        train = net.trains[train_id]
        occs = sorted((o for o in result.occupancies if o.train_id == train_id), key=lambda o: o.entry)
        calls = {c.station: c for c in result.calls if c.train_id == train_id}
        state = None
        if at < stops[0].sched_dep:
            state = _state(train, "not_started", stops[0].station, None, 0)
        else:
            for k, occ in enumerate(occs):
                here, nxt = stops[k], stops[k + 1]
                waiting_delay = max(calls[here.station].arr_delay or 0, at - here.sched_dep, 0)
                if at < occ.requested:
                    state = _state(train, "at_station", here.station, None, waiting_delay)
                elif at < occ.entry:
                    state = _state(train, "waiting_at_signal", here.station, None, waiting_delay)
                elif at < occ.exit:
                    delay = max(occ.entry - here.sched_dep, at - nxt.sched_arr, 0)
                    windows = _stop_windows(occ, disruptions or [])
                    stood = sum(max(0, min(at, e) - max(occ.entry, s)) for s, e in windows)
                    run = max(1, occ.exit - occ.entry - occ.stopped_min)
                    progress = min(1.0, max(0.0, (at - occ.entry - stood) / run))
                    state = _state(train, "in_section", occ.section_id, round(progress, 3), delay)
                    state["next_station"] = nxt.station
                    state["stopped"] = any(s <= at < e for s, e in windows)
                if state is not None:
                    break
            if state is None:
                state = _state(train, "arrived", stops[-1].station, None, result.final_delay(train_id))
        if estimated:
            here = state["location"] if state["status"] != "in_section" else net.sections[state["location"]].from_station
            nxt = state["next_station"] or here
            state["interpolated"] = state["status"] not in ("not_started", "arrived") and (
                (train_id, here) in estimated or (train_id, nxt) in estimated)
        states.append(state)
    return states


def _state(train, status, location, progress, delay) -> dict:
    return {"train_id": train.train_id, "train_type": train.train_type, "priority": train.priority,
            "status": status, "location": location, "progress": progress, "next_station": None,
            "current_delay_min": int(delay), "stopped": False}


def _stop_windows(occ, disruptions: list[Disruption]) -> list[tuple[int, int]]:
    """[start, end) of the stoppages the simulator applied to this trip (rng=None rule)."""
    if not occ.stopped_min:
        return []
    return [(d.start, d.start + d.duration) for d in disruptions
            if d.event_type == "STOPPAGE" and d.train_id == occ.train_id and d.location == occ.section_id
            and occ.entry <= d.start < occ.exit]


def kpis(states: list[dict], conflicts: int) -> dict:
    active = [s for s in states if s["status"] not in ("not_started", "arrived")]
    delays = [s["current_delay_min"] for s in active]
    return {"active_trains": len(active),
            "delayed_trains": sum(1 for d in delays if d > 0),
            "conflicts": conflicts,
            "avg_delay_min": round(sum(delays) / len(delays), 2) if delays else 0.0}


# ---------------------------------------------------------------------------
# conflicts + ML
# ---------------------------------------------------------------------------
def conflicts_view(net: RailNetwork, at: int, known: list[Disruption], predictor=None,
                   route_overrides: dict | None = None, holds: dict | None = None,
                   previous_overrides: dict | None = None, previous_holds: dict | None = None,
                   estimated: set[tuple[str, str]] | None = None, ml_off_note: str | None = None) -> dict:
    """Detector on the plan (timetable + known events + any accepted controller plan).

    ML features describe the unchanged timetable plan, as in training."""
    plan = project_plan(net, at, known, route_overrides, holds)
    conflicts = detect_conflicts(net, plan)
    rows, ml_note = {}, None
    disruptions = sorted(known, key=lambda d: d.start)
    if ml_off_note:
        ml_note = ml_off_note
    elif predictor is None:
        ml_note = "predictor models not found; run python -m ml.train"
    elif not disruptions:
        ml_note = "no disruption known at this time; the model is trained on disrupted runs only"
    else:
        from app.services.datagen import plan_features
        for row in plan_features(net, at, known, disruptions[0]):
            rows[(row["train_id"], row["section_id"])] = (row, predictor.predict(row))

    def prediction(key):
        if key not in rows:
            return None
        _row, p = rows[key]
        return {"conflict_probability": round(p["conflict_probability"], 4),
                "flagged": bool(p["conflict_predicted"]), "threshold": round(p["threshold"], 4),
                "top_drivers": explainer.describe_all(p["top_drivers"])}

    out = []
    for c in conflicts:
        out.append({
            "conflict_id": c.conflict_id, "section_id": c.section_id,
            "earlier_train": c.earlier, "later_train": c.later, "conflict_type": c.conflict_type,
            "window_start": format_time(c.window_start), "window_end": format_time(c.window_end),
            "minutes_short": c.minutes_short, "time_to_conflict_min": c.time_to_conflict,
            "severity": c.severity, "event_id": c.event_id,
            "prediction": prediction((c.later, c.section_id)),
            "certainty": certainty(net, c, estimated),
        })
    flagged_by_rules = {(c.later, c.section_id) for c in conflicts}
    watchlist = []
    for key, (row, p) in rows.items():
        if p["conflict_predicted"] and key not in flagged_by_rules:
            watchlist.append({"train_id": key[0], "section_id": key[1],
                              "time_to_section_min": row["time_to_section_min"],
                              **prediction(key)})
    # with an accepted plan: replay it on the known events (rng=None) and compare the train's
    # wait before that B-C / A-B / ... trip with the plan it replaced (or no plan if none).
    # wait 0 in the plan -> resolved; lower but not 0 -> reduced.
    has_plan = bool(route_overrides or holds)
    plan_replay = simulate(net, known, route_overrides=route_overrides, holds=holds) if has_plan else None
    base_replay = (simulate(net, known, route_overrides=previous_overrides or None, holds=previous_holds or None)
                   if has_plan else None)

    def wait_before(replay, item) -> int:
        sec = net.sections[item["section_id"]]
        trip = next(o for o in replay.occupancies if o.train_id == item["train_id"]
                    and (net.sections[o.section_id].from_station, net.sections[o.section_id].to_station)
                    == (sec.from_station, sec.to_station))
        return trip.wait

    for item in watchlist:
        item["resolved_by_plan"] = False
        item["reduced_by_plan"] = False
        item["plan_wait_min"] = None
        item["baseline_wait_min"] = None
        if has_plan:
            item["plan_wait_min"] = wait_before(plan_replay, item)
            item["baseline_wait_min"] = wait_before(base_replay, item)
            item["resolved_by_plan"] = item["plan_wait_min"] == 0
            item["reduced_by_plan"] = 0 < item["plan_wait_min"] < item["baseline_wait_min"]
    watchlist.sort(key=lambda w: (w["resolved_by_plan"], w["reduced_by_plan"], -w["conflict_probability"]))
    if ml_note is None and ml_off_note is None and (route_overrides or holds):
        ml_note = ("an accepted plan is in force; the model's features describe the timetable plan "
                   "without it (it was trained on runs with no re-planning), so its flags may be outdated")
    return {"conflicts": out, "ml_watchlist": watchlist, "ml_note": ml_note, "_raw": conflicts}


# ---------------------------------------------------------------------------
# optimisation + recommendation
# ---------------------------------------------------------------------------
def certainty(net: RailNetwork, c, estimated: set[tuple[str, str]] | None) -> str:
    """FIRM, or ESTIMATED when the clash rests on an interpolated / estimated time (REAL replay)."""
    if not estimated:
        return "FIRM"
    sec = net.sections[c.section_id]
    keys = [(c.later, sec.from_station)] + ([(c.earlier, sec.to_station)] if c.earlier else [(c.later, sec.to_station)])
    return "ESTIMATED" if any(k in estimated for k in keys) else "FIRM"


def optimize_view(net: RailNetwork, at: int, known: list[Disruption],
                  base_holds: dict | None = None, base_overrides: dict | None = None) -> dict:
    """Compare strategies at `at`. With an accepted plan (base_*), started trips stay as that
    plan made them and the baselines keep it; the strategies re-plan the future."""
    allowed, unavailable = available_strategies(net)
    results = compare(net, at, known, base_holds=base_holds or None, base_overrides=base_overrides or None,
                      strategies=allowed)
    rows = [_result_row(r) for r in results]
    base = next(r for r in results if r.name == "NO_REPLANNING")
    candidates = [r for r in results if r.kind == "strategy" and r.replay is not None]
    rec = None
    if candidates:
        best = min(candidates, key=lambda r: (r.weighted_delay, len(r.actions), STRATEGY_ORDER[r.name]))
        conflicts = detect_conflicts(net, project_plan(net, at, known, base_overrides, base_holds))
        rec = {"strategy": best.name, "status": best.status, "actions": best.actions,
               "weighted_delay": best.weighted_delay, "total_delay": best.total_delay,
               "delays": best.delays,
               "explanation": explainer.explain(net, best, base, results, conflicts, unavailable, known),
               "_holds": best.holds, "_route_overrides": best.route_overrides}
    return {"results": rows, "recommendation": rec, "unavailable": unavailable,
            "ranking": [r.name for r in sorted(candidates, key=lambda r: (r.weighted_delay, len(r.actions),
                                                                           STRATEGY_ORDER[r.name]))]}


def _result_row(r) -> dict:
    return {"name": r.name, "kind": r.kind, "status": r.status, "solve_seconds": r.solve_seconds,
            "message": r.message, "weighted_delay": r.weighted_delay, "total_delay": r.total_delay,
            "delays": r.delays, "throughput_trains_per_hour": r.throughput,
            "violations": len(r.violations) if r.replay is not None else None,
            "actions": r.actions}


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------
def timeline_rows(net: RailNetwork, result: SimResult, disruptions: list[Disruption] | None = None,
                  estimated: set[tuple[str, str]] | None = None) -> list[dict]:
    """One row per section trip, ready to draw on a time-distance chart.

    stops      [start, end) windows the train stood still inside the section (stoppages)
    delay_min  exit compared with the timetabled arrival at the row's end station
    alternate  the trip ran on a standby (alternate) line
    """
    rows = []
    for o in sorted(result.occupancies, key=lambda o: (o.train_id, o.entry)):
        sec = net.sections[o.section_id]
        sched_arr = next((s.sched_arr for s in net.schedules[o.train_id] if s.station == sec.to_station), None)
        rows.append({"train_id": o.train_id, "section_id": o.section_id,
                     "from_station": sec.from_station, "to_station": sec.to_station,
                     "from_km": net.stations[sec.from_station].km_from_start,
                     "to_km": net.stations[sec.to_station].km_from_start,
                     "entry_min": o.entry, "exit_min": o.exit,
                     "entry": format_time(o.entry), "exit": format_time(o.exit),
                     "wait_min": o.wait, "stopped_min": o.stopped_min,
                     "stops": [{"start_min": s, "end_min": e} for s, e in _stop_windows(o, disruptions or [])],
                     "delay_min": None if sched_arr is None else o.exit - sched_arr,
                     "alternate": sec.status == "standby",
                     "interpolated": bool(estimated) and ((o.train_id, sec.from_station) in estimated
                                                          or (o.train_id, sec.to_station) in estimated)})
    return rows


def planned_timeline(net: RailNetwork) -> list[dict]:
    """The timetable as occupancies (no disruptions: the normal day is conflict-free)."""
    return timeline_rows(net, simulate(net))


def closure_blocks(net: RailNetwork, events: list[Disruption]) -> list[dict]:
    """Posted track closures (known once posted) as blocks for the chart."""
    out = []
    for e in events:
        if e.event_type != "TRACK_UNAVAILABLE" or e.location not in net.sections:
            continue
        sec = net.sections[e.location]
        out.append({"event_id": e.event_id, "section_id": e.location,
                    "from_km": net.stations[sec.from_station].km_from_start,
                    "to_km": net.stations[sec.to_station].km_from_start,
                    "start_min": e.start, "end_min": e.end, "start": format_time(e.start), "end": format_time(e.end)})
    return out


# ---------------------------------------------------------------------------
# closures on occupied sections
# ---------------------------------------------------------------------------
def closure_conflict(timeline: SimResult, section_id: str, start: int) -> str | None:
    """A closure may not start while a train is inside the section (the model cannot strand
    a train). Returns a clear message with the first start after the section clears, or None."""
    def inside(t: int):
        return [o for o in timeline.occupancies if o.section_id == section_id and o.entry < t < o.exit]

    occupants = inside(start)
    if not occupants:
        return None
    clear = start
    while inside(clear):
        clear = max(o.exit for o in inside(clear))
    names = " and ".join(sorted(o.train_id for o in occupants))
    verb = "is" if len(occupants) == 1 else "are"
    return (f"{names} {verb} inside {section_id} at {format_time(start)}; closing an occupied section "
            f"isn't modelled - choose a start after it clears ({format_time(clear)})")
