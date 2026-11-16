"""Conflicts and Alerts (page 5): the full alert lists at a clock time and the alert history of
the current scenario. Plain Python; the route in app/api/routes.py only wires it up.

Current lists come from the same detector view the console uses (live.conflicts_view):
rule-based conflicts (FIRM -> CRITICAL / WARNING), uncertain clashes (REAL replay: they rest on
an interpolated or ESTIMATED time), the ML watchlist (active / reduced by plan / resolved by plan)
and posted track closures. Every row carries template text (Phase 7 wording: the detector's
Reason sentence may say "because", ML driver sentences never do).

History: the same detection is re-run at every sim minute from the first timetabled departure
to the clock, each time with the knowledge of that minute:
  - STOPPAGE / DELAY are known from their start (as everywhere else in the API);
  - a planned event (TRACK_UNAVAILABLE, ...) is known from the clock at which it was posted
    (`posted_at`, sent by the UI); without a posting clock it counts as known from the start;
  - the accepted plan in force is the last one accepted (decision log order) whose optimizer
    run was at or before that minute; the plan it replaced is its baseline (watchlist states).
An alert appears / clears at the first minute it is present / absent. The cause is the event or
decision that became effective in that minute; otherwise the clash window passed (cleared at or
after the train's planned entry), the REAL forecast was updated with recorded movement, or the
projection moved on with the clock. Nothing here is typed by hand: every number and time comes
from the detector, the events and the decision log.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services import live
from app.services.explainer.recommendation import reason_text
from app.services.network import RailNetwork, format_time, parse_time

PLANNED_TYPES = ("TRACK_UNAVAILABLE", "PLATFORM_UNAVAILABLE")
CATEGORIES = ("CONFLICT", "UNCERTAIN", "ML_WATCH", "CLOSURE")
ML_STEP = 5    # history: the ML watchlist is re-scored every 5 sim minutes and at every event / decision
UNCERTAIN_NOTE = ("It rests on an interpolated or estimated time, so it is listed as uncertain, "
                  "not as an alert.")


# ---------------------------------------------------------------------------
# keys and rows
# ---------------------------------------------------------------------------
def conflict_key(c: dict) -> str:
    return f"C:{c['conflict_type']}:{c['section_id']}:{c['earlier_train'] or '-'}:{c['later_train']}"


def ml_key(w: dict) -> str:
    return f"ML:{w['train_id']}:{w['section_id']}"


def closure_key(event_id: str) -> str:
    return f"CL:{event_id}"


def _conflict_row(c: dict) -> dict:
    uncertain = c.get("certainty") == "ESTIMATED"
    text = reason_text(c) + (" " + UNCERTAIN_NOTE if uncertain else "")
    trains = [t for t in (c["earlier_train"], c["later_train"]) if t]
    return {"key": conflict_key(c), "category": "UNCERTAIN" if uncertain else "CONFLICT",
            "severity": "UNCERTAIN" if uncertain else c["severity"], "status": "ACTIVE",
            "conflict_type": c["conflict_type"], "section_id": c["section_id"], "trains": trains,
            "title": f"{c['later_train']} {c['conflict_type'].lower()} on {c['section_id']}",
            "explanation": text, "drivers": (c.get("prediction") or {}).get("top_drivers") or [],
            "window_start": c["window_start"], "window_end": c["window_end"],
            "minutes_short": c["minutes_short"], "time_to_conflict_min": c["time_to_conflict_min"],
            "event_id": c.get("event_id"), "prediction": c.get("prediction")}


def _ml_row(w: dict) -> dict:
    status = "RESOLVED" if w["resolved_by_plan"] else "REDUCED" if w["reduced_by_plan"] else "ACTIVE"
    text = (f"The rule-based detector does not flag {w['train_id']} on {w['section_id']}; the model scores "
            f"{w['conflict_probability']} (threshold {w['threshold']}).")
    if status == "RESOLVED":
        text += f" In the accepted plan's replay {w['train_id']} waits {w['plan_wait_min']} min before this trip."
    elif status == "REDUCED":
        text += (f" The accepted plan lowers its wait before this trip from {w['baseline_wait_min']} to "
                 f"{w['plan_wait_min']} min.")
    return {"key": ml_key(w), "category": "ML_WATCH", "severity": "WATCH", "status": status,
            "conflict_type": None, "section_id": w["section_id"], "trains": [w["train_id"]],
            "title": f"AI watch: {w['train_id']} on {w['section_id']}", "explanation": text,
            "drivers": w.get("top_drivers") or [], "window_start": None, "window_end": None,
            "minutes_short": None, "time_to_conflict_min": w.get("time_to_section_min"),
            "event_id": None, "prediction": {k: w[k] for k in ("conflict_probability", "threshold")},
            "plan_wait_min": w.get("plan_wait_min"), "baseline_wait_min": w.get("baseline_wait_min")}


def _closure_rows(net: RailNetwork, events, conflicts: list[dict], at: int) -> list[dict]:
    out = []
    for e in events:
        if e.event_type != "TRACK_UNAVAILABLE" or e.location not in net.sections or at >= e.end:
            continue
        hit = sorted({c["later_train"] for c in conflicts if c.get("event_id") == e.event_id})
        text = f"{e.location} is closed ({e.event_id}) from {format_time(e.start)} to {format_time(e.end)}."
        text += (f" Planned to enter while it is closed: {', '.join(hit)}." if hit
                 else " No train is planned to enter it while it is closed.")
        out.append({"key": closure_key(e.event_id), "category": "CLOSURE", "severity": "INFO",
                    "status": "ACTIVE" if at >= e.start else "UPCOMING", "conflict_type": None,
                    "section_id": e.location, "trains": hit, "title": f"{e.location} closed ({e.event_id})",
                    "explanation": text, "drivers": [], "window_start": format_time(e.start),
                    "window_end": format_time(e.end), "minutes_short": None,
                    "time_to_conflict_min": e.start - at, "event_id": e.event_id, "prediction": None})
    return out


# ---------------------------------------------------------------------------
# what the controller knew at minute t
# ---------------------------------------------------------------------------
def known_at(store, t: int) -> list:
    """Events known at minute t for the history (planned events: from their posting clock)."""
    out = []
    for e in store.events:
        if e.event_type in PLANNED_TYPES:
            if store.posted_at.get(e.event_id, -1) <= t:
                out.append(e)
        elif e.start <= t:
            out.append(e)
    return out


@dataclass
class PlanAt:
    rec_id: str | None
    holds: dict
    overrides: dict
    prev_holds: dict
    prev_overrides: dict


def plan_at(store, t: int) -> PlanAt:
    """The accepted plan in force at minute t and the plan it replaced."""
    current = None
    for d in store.decision_log:
        if d["decision"] == "accept" and d["at"] <= t:
            current = d
    if current is None:
        return PlanAt(None, {}, {}, {}, {})
    rec = store.recommendations[current["recommendation_id"]]
    prev = store.recommendations.get(current["replaces"]) if current.get("replaces") else None
    return PlanAt(rec.rec_id, dict(rec.holds), dict(rec.route_overrides),
                  dict(prev.holds) if prev else {}, dict(prev.route_overrides) if prev else {})


def first_departure(net: RailNetwork) -> int:
    times = [s.sched_dep if s.sched_dep is not None else s.sched_arr
             for stops in net.schedules.values() for s in stops]
    return min(t for t in times if t is not None)


# ---------------------------------------------------------------------------
# current lists
# ---------------------------------------------------------------------------
def current(store, at: int, predictor=None, ml_off: str | None = None, estimated=None) -> dict:
    net = store.planning_network(at)
    known = store.known_events(at)
    view = live.conflicts_view(net, at, known, predictor, store.route_overrides, store.holds,
                               store.previous_overrides, store.previous_holds, estimated, ml_off)
    rows = [_conflict_row(c) for c in view["conflicts"]]
    rows += [_ml_row(w) for w in view["ml_watchlist"]]
    rows += _closure_rows(net, known, view["conflicts"], at)
    return {"rows": rows, "ml_note": view["ml_note"]}


def _keys_at(store, t: int, predictor, ml_off, estimated, carry_ml: dict | None = None) -> dict[str, dict]:
    """Alert rows present at minute t. With carry_ml (predictor None), the ML rows of the last
    scored minute are carried forward instead of re-scoring (the model is slow: SHAP per row)."""
    net = store.planning_network(t)
    known = known_at(store, t)
    p = plan_at(store, t)
    view = live.conflicts_view(net, t, known, predictor, p.overrides, p.holds, p.prev_overrides,
                               p.prev_holds, estimated, ml_off)
    rows = [_conflict_row(c) for c in view["conflicts"]]
    rows += [_ml_row(w) for w in view["ml_watchlist"]]
    rows += [r for r in _closure_rows(net, known, view["conflicts"], t) if r["status"] == "ACTIVE"]
    if carry_ml:
        rows += list(carry_ml.values())
    return {r["key"]: r for r in rows}


def breakpoints(store) -> set[int]:
    """Minutes at which an event becomes known or an accepted plan takes effect."""
    out = {d["at"] for d in store.decision_log if d["decision"] == "accept"}
    for e in store.events:
        k = store.posted_at.get(e.event_id) if e.event_type in PLANNED_TYPES else e.start
        if k is not None:
            out.add(k)
    return out


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------
def _effective(store, t_from: int, t_to: int) -> list[dict]:
    """Events and accepted decisions that became effective in (t_from, t_to]."""
    out = []
    for e in store.events:
        k = (store.posted_at.get(e.event_id, -1) if e.event_type in PLANNED_TYPES else e.start)
        if t_from < k <= t_to:
            out.append({"kind": "EVENT", "id": e.event_id,
                        "text": f"{e.event_id} ({e.event_type}, {e.train_id or e.location}) became known"})
    for d in store.decision_log:
        if d["decision"] == "accept" and t_from < d["at"] <= t_to:
            who = f" by {d['decided_by']}" if d.get("decided_by") else ""
            out.append({"kind": "DECISION", "id": d["recommendation_id"],
                        "text": f"plan {d['recommendation_id']} ({d['strategy']}) accepted{who}"})
    return out


def _cause(store, t_prev: int, t: int, row: dict, cleared: bool, first: bool = False) -> dict:
    if first and not cleared:
        return {"kind": "START", "ids": [], "text": "present from the start of the projection (first departure)"}
    found = _effective(store, t_prev, t)
    if found:
        return {"kind": found[0]["kind"], "ids": [f["id"] for f in found],
                "text": "; ".join(f["text"] for f in found)}
    if cleared and row.get("window_start") and row["category"] in ("CONFLICT", "UNCERTAIN") \
            and t >= parse_time(row["window_start"]):
        return {"kind": "TIME", "ids": [], "text": f"clash window passed (planned entry {row['window_start']})"}
    if cleared and row["category"] == "CLOSURE":
        return {"kind": "TIME", "ids": [], "text": f"closure ended at {row['window_end']}"}
    if store.is_replay:
        return {"kind": "FORECAST", "ids": [], "text": "forecast updated with recorded movement"}
    return {"kind": "TIME", "ids": [], "text": "projection moved on with the clock"}


def history(store, at: int, predictor=None, ml_off: str | None = None, estimated=None) -> list[dict]:
    """Alert episodes (appeared / cleared, sim time and cause) from the first departure to `at`."""
    start = min(first_departure(store.network()), at)
    open_: dict[str, dict] = {}
    episodes: list[dict] = []
    prev_t = start - 1
    marks = breakpoints(store)
    ml_rows: dict[str, dict] = {}
    for t in range(start, at + 1):
        score = predictor is not None and ((t - start) % ML_STEP == 0 or t in marks or t == at)
        if score:
            rows = _keys_at(store, t, predictor, ml_off, estimated)
            ml_rows = {k: r for k, r in rows.items() if r["category"] == "ML_WATCH"}
        else:
            rows = _keys_at(store, t, None, ml_off or "-", estimated, carry_ml=ml_rows)
        for key, row in rows.items():
            if key not in open_:
                ep = {"key": key, "category": row["category"], "severity": row["severity"],
                      "title": row["title"], "section_id": row["section_id"], "trains": row["trains"],
                      "appeared": format_time(t),
                      "appeared_cause": _cause(store, prev_t, t, row, False, first=(t == start)),
                      "cleared": None, "cleared_cause": None, "active": True}
                open_[key] = ep
                episodes.append(ep)
            else:
                open_[key]["severity"] = row["severity"]
                open_[key]["category"] = row["category"]
            open_[key]["_row"] = row
        for key in [k for k in open_ if k not in rows]:
            ep = open_.pop(key)
            ep["cleared"] = format_time(t)
            ep["cleared_cause"] = _cause(store, prev_t, t, ep["_row"], True)
            ep["active"] = False
        prev_t = t
    for ep in episodes:
        ep.pop("_row", None)
    episodes.sort(key=lambda e: (e["appeared"], e["key"]))
    return episodes


# ---------------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------------
def alerts_view(store, at: int, predictor=None, ml_off: str | None = None, estimated=None,
                acknowledged: dict | None = None) -> dict:
    cur = current(store, at, predictor, ml_off, estimated)
    hist = history(store, at, predictor, ml_off, estimated)
    acknowledged = acknowledged or {}
    for r in cur["rows"]:
        r["acknowledged"] = acknowledged.get(r["key"])
    for e in hist:
        e["acknowledged"] = acknowledged.get(e["key"])
    counts = {c: sum(1 for r in cur["rows"] if r["category"] == c) for c in CATEGORIES}
    return {"current": cur["rows"], "history": hist, "ml_note": cur["ml_note"], "counts": counts,
            "posting_clock_missing": sorted(e.event_id for e in store.events
                                            if e.event_type in PLANNED_TYPES and e.event_id not in store.posted_at)}


__all__ = ["alerts_view", "current", "history", "known_at", "plan_at", "conflict_key", "ml_key",
           "closure_key"]
