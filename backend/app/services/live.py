"""Views of a scenario at a clock time: train states, conflicts + ML, plans.

Plain Python (no FastAPI) so it can be tested directly. All SIMULATED.
"""
from __future__ import annotations

from app.services.conflicts import detect_conflicts, project_plan
from app.services.network import RailNetwork, format_time
from app.services.optimizer import compare
from app.services.optimizer.solver import STRATEGIES
from app.services.simulator import Disruption, SimResult, simulate

STRATEGY_ORDER = {s.name: k for k, s in enumerate(STRATEGIES)}


# ---------------------------------------------------------------------------
# train states
# ---------------------------------------------------------------------------
def train_states(net: RailNetwork, result: SimResult, at: int) -> list[dict]:
    """Where every train is at `at` in a simulated timeline, and how late it is.

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
                    state = _state(train, "in_section", occ.section_id,
                                   round((at - occ.entry) / (occ.exit - occ.entry), 3), delay)
                    state["next_station"] = nxt.station
                if state is not None:
                    break
            if state is None:
                state = _state(train, "arrived", stops[-1].station, None, result.final_delay(train_id))
        states.append(state)
    return states


def _state(train, status, location, progress, delay) -> dict:
    return {"train_id": train.train_id, "train_type": train.train_type, "priority": train.priority,
            "status": status, "location": location, "progress": progress, "next_station": None,
            "current_delay_min": int(delay)}


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
                   route_overrides: dict | None = None, holds: dict | None = None) -> dict:
    """Detector on the plan (timetable + known events + any accepted controller plan).

    ML features describe the unchanged timetable plan, as in training."""
    plan = project_plan(net, at, known, route_overrides, holds)
    conflicts = detect_conflicts(net, plan)
    rows, ml_note = {}, None
    disruptions = sorted(known, key=lambda d: d.start)
    if predictor is None:
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
                "top_drivers": p["top_drivers"]}

    out = []
    for c in conflicts:
        out.append({
            "conflict_id": c.conflict_id, "section_id": c.section_id,
            "earlier_train": c.earlier, "later_train": c.later, "conflict_type": c.conflict_type,
            "window_start": format_time(c.window_start), "window_end": format_time(c.window_end),
            "minutes_short": c.minutes_short, "time_to_conflict_min": c.time_to_conflict,
            "severity": c.severity, "event_id": c.event_id,
            "prediction": prediction((c.later, c.section_id)),
        })
    flagged_by_rules = {(c.later, c.section_id) for c in conflicts}
    watchlist = []
    for key, (row, p) in rows.items():
        if p["conflict_predicted"] and key not in flagged_by_rules:
            watchlist.append({"train_id": key[0], "section_id": key[1],
                              "time_to_section_min": row["time_to_section_min"],
                              **prediction(key)})
    watchlist.sort(key=lambda w: -w["conflict_probability"])
    if ml_note is None and (route_overrides or holds):
        ml_note = ("an accepted plan is in force; the model's features describe the timetable plan "
                   "without it (it was trained on runs with no re-planning), so its flags may be outdated")
    return {"conflicts": out, "ml_watchlist": watchlist, "ml_note": ml_note, "_raw": conflicts}


# ---------------------------------------------------------------------------
# optimisation + recommendation
# ---------------------------------------------------------------------------
def optimize_view(net: RailNetwork, at: int, known: list[Disruption]) -> dict:
    results = compare(net, at, known)
    rows = [_result_row(r) for r in results]
    base = next(r for r in results if r.name == "NO_REPLANNING")
    candidates = [r for r in results if r.kind == "strategy" and r.replay is not None]
    rec = None
    if candidates:
        best = min(candidates, key=lambda r: (r.weighted_delay, len(r.actions), STRATEGY_ORDER[r.name]))
        conflicts = detect_conflicts(net, project_plan(net, at, known))
        rec = {"strategy": best.name, "status": best.status, "actions": best.actions,
               "weighted_delay": best.weighted_delay, "total_delay": best.total_delay,
               "delays": best.delays,
               "explanation": explain(net, best, base, conflicts),
               "_holds": best.holds, "_route_overrides": best.route_overrides}
    return {"results": rows, "recommendation": rec}


def _result_row(r) -> dict:
    return {"name": r.name, "kind": r.kind, "status": r.status, "solve_seconds": r.solve_seconds,
            "message": r.message, "weighted_delay": r.weighted_delay, "total_delay": r.total_delay,
            "delays": r.delays, "throughput_trains_per_hour": r.throughput,
            "violations": len(r.violations) if r.replay is not None else None,
            "actions": r.actions}


def explain(net: RailNetwork, best, base, conflicts) -> dict:
    """Template explanation built only from computed numbers (Phase 7 enriches it)."""
    critical = [c for c in conflicts if c.severity == "CRITICAL"] or conflicts
    if critical:
        c = critical[0]
        if c.conflict_type == "CLOSURE":
            reason = (f"{c.later} is planned to enter {c.section_id} at {format_time(c.window_start)} "
                      f"while it is closed ({c.event_id}) until {format_time(c.window_end)}.")
        else:
            reason = (f"{c.later} is planned to enter {c.section_id} at {format_time(c.window_start)} but "
                      f"{c.earlier} holds it until {format_time(c.window_end)} ({c.conflict_type}, "
                      f"{c.minutes_short} min short, {c.severity}, in {c.time_to_conflict} min).")
    else:
        reason = "No conflict is detected from the known events at this time."
    late = ", ".join(f"{t} {d} min" for t, d in base.delays.items() if d) or "no train late"
    counterfactual = (f"Without re-planning: weighted delay {base.weighted_delay}, "
                      f"total delay {base.total_delay} min ({late}).")
    d_total = best.total_delay - base.total_delay
    d_weighted = best.weighted_delay - base.weighted_delay
    if d_weighted < 0:
        impact = (f"{best.name}: weighted delay {best.weighted_delay} ({d_weighted:+d}), "
                  f"total delay {best.total_delay} min ({d_total:+d} min).")
    else:
        impact = f"No strategy improves on no re-planning (weighted delay {best.weighted_delay})."
    solver = (f"CP-SAT status {best.status}: proven optimal for the {best.name} model."
              if best.status == "OPTIMAL" else
              f"CP-SAT status {best.status}: feasible, not proven optimal.")
    return {"reason": reason, "counterfactual": counterfactual, "expected_impact": impact,
            "solver": solver, "delta_total_delay_min": d_total, "delta_weighted_delay": d_weighted,
            "note": "Template text from simulated numbers; the controller decides."}


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------
def timeline_rows(net: RailNetwork, result: SimResult) -> list[dict]:
    rows = []
    for o in sorted(result.occupancies, key=lambda o: (o.train_id, o.entry)):
        sec = net.sections[o.section_id]
        rows.append({"train_id": o.train_id, "section_id": o.section_id,
                     "from_station": sec.from_station, "to_station": sec.to_station,
                     "from_km": net.stations[sec.from_station].km_from_start,
                     "to_km": net.stations[sec.to_station].km_from_start,
                     "entry_min": o.entry, "exit_min": o.exit,
                     "entry": format_time(o.entry), "exit": format_time(o.exit),
                     "wait_min": o.wait, "stopped_min": o.stopped_min})
    return rows


def planned_timeline(net: RailNetwork) -> list[dict]:
    """The timetable as occupancies (no disruptions: the normal day is conflict-free)."""
    return timeline_rows(net, simulate(net))
