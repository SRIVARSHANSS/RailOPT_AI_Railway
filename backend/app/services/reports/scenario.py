"""Scenario report (PDF + CSV) for the current scenario at a clock time.

The data is gathered by calling the API's own route functions (scenario, state, conflicts,
timeline) with the same store, so every number in the report is the number those endpoints
return; recommendations carry the Phase 7 `plain_text` stored with them, decisions the user who
took them. Nothing is recomputed for the report and no number is typed here.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from app.services.explainer.recommendation import DISCLAIMER, reason_text

from . import charts
from .pdf import PageBreak, Spacer, boxed, build, figure, frame_width, p, styles, table


def _dump(x) -> dict:
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


def scenario_data(store, at: str, user, predictor=None, now: datetime | None = None) -> dict:
    """Everything the report shows, from the API payloads at clock `at`."""
    from app.api import routes
    scn = _dump(routes.scenario(at=at, store=store, _user=user))
    state = _dump(routes.state(at=at, store=store, _user=user))
    conflicts = _dump(routes.conflicts(at=at, store=store, predictor=predictor, _user=user))
    tl = _dump(routes.timeline(store=store, _user=user))
    from app.api.alerts_routes import compute
    history = compute(store, _min(at), predictor)["history"]
    recs = []
    for rec in store.recommendations.values():
        expl = (rec.payload or {}).get("explanation") or {}
        recs.append({"recommendation_id": rec.rec_id, "strategy": rec.strategy, "at_min": rec.at,
                     "decision": rec.decision, "weighted_delay": (rec.payload or {}).get("weighted_delay"),
                     "status": (rec.payload or {}).get("status"), "plain_text": expl.get("plain_text")})
    trains = {t["train_id"]: t for t in state["trains"]}
    per_train = []
    for tid, t in trains.items():
        rows = [r for r in tl["actual"] if r["train_id"] == tid]
        last = max(rows, key=lambda r: r["exit_min"]) if rows else None
        per_train.append({"train_id": tid, "train_type": t["train_type"], "priority": t["priority"],
                          "status": t["status"], "location": t["location"],
                          "delay_at_clock_min": t["current_delay_min"],
                          "final_arrival": last["exit"] if last else None,
                          "final_delay_min": last["delay_min"] if last else None,
                          "wait_min": sum(r["wait_min"] for r in rows),
                          "standing_still_min": sum(r["stopped_min"] for r in rows)})
    stations = sorted(tl["stations"], key=lambda s: s["km"])
    now = now or datetime.now(timezone.utc)
    return {
        "meta": {"data_label": scn["data_label"], "scenario_version": scn["scenario_version"], "at": at,
                 "timetable": scn["timetable"], "mode": scn["mode"],
                 "replay_date": (scn.get("replay") or {}).get("date"),
                 "generated_at_utc": now.isoformat(timespec="seconds"),
                 "generated_by": getattr(user, "email", None), "generated_by_role": getattr(user, "role", None),
                 "corridor": " → ".join(s["code"] for s in stations)},
        "kpis": state["kpis"], "plan": state["plan"], "events": scn["events"],
        "conflicts": conflicts["conflicts"], "ml_watchlist": conflicts["ml_watchlist"], "ml_note": conflicts["ml_note"],
        "alert_history": history, "recommendations": recs, "decisions": scn["decision_log"], "per_train": per_train,
        "holds": scn["holds"], "route_overrides": scn["route_overrides"],
        "_timeline": tl, "_trains": trains,
    }


# ---------------------------------------------------------------------------
# CSV: one file, long format (section, item, field, value) so every block fits one layout
# ---------------------------------------------------------------------------
def scenario_csv(d: dict) -> str:
    buf = io.StringIO()
    buf.write("﻿")                          # BOM: spreadsheet programs then read UTF-8 (→)
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "item", "field", "value"])

    def put(section, item, record: dict):
        for k, v in record.items():
            w.writerow([section, item, k, "" if v is None else v])

    put("meta", "", d["meta"])
    put("kpis", d["meta"]["at"], d["kpis"])
    for e in d["events"]:
        put("event", e["event_id"], e)
    for c in d["conflicts"]:
        rec = {k: v for k, v in c.items() if k != "prediction"}
        if c.get("prediction"):
            rec["model_probability"] = c["prediction"]["conflict_probability"]
        put("conflict", f"{c['section_id']}:{c['later_train']}", rec)
    for wl in d["ml_watchlist"]:
        put("ml_watch", f"{wl['section_id']}:{wl['train_id']}",
            {k: v for k, v in wl.items() if k != "top_drivers"})
    for t in d["per_train"]:
        put("train", t["train_id"], t)
    for i, h in enumerate(d["alert_history"], 1):
        put("alert", f"{i}:{h['key']}", {"category": h["category"], "severity": h["severity"], "title": h["title"],
                                          "appeared": h["appeared"], "appeared_cause": h["appeared_cause"]["text"],
                                          "cleared": h["cleared"],
                                          "cleared_cause": (h["cleared_cause"] or {}).get("text")})
    for r in d["recommendations"]:
        put("recommendation", r["recommendation_id"], r)
    for i, x in enumerate(d["decisions"], 1):
        put("decision", str(i), x)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _hhmm(m) -> str:
    return "" if m is None else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def scenario_pdf(d: dict) -> bytes:
    st = styles()
    W = frame_width()
    m = d["meta"]
    story = [p("Scenario report", "title", st),
             p(f"{m['data_label']} · scenario version {m['scenario_version']} · sim time {m['at']}", "small", st),
             Spacer(1, 6)]
    mode = m["mode"] + (f", recorded day {m['replay_date']}" if m.get("replay_date") else "")
    story.append(table([["Field", "Value"],
                        ["Data label", m["data_label"]], ["Timetable", f"{m['timetable']} ({mode})"],
                        ["Corridor", m["corridor"]], ["Scenario version", m["scenario_version"]],
                        ["Sim time (clock)", m["at"]], ["Generated at (UTC)", m["generated_at_utc"]],
                        ["Generated by", f"{m['generated_by']} ({m['generated_by_role']})"]],
                       [W * 0.28, W * 0.72], st=st))
    story.append(Spacer(1, 4))
    story.append(boxed([p(DISCLAIMER, "small", st)]))

    k = d["kpis"]
    story += [p("Key figures at the clock", "h1", st),
              table([["Active trains", "Delayed trains", "Conflicts (firm)", "Average delay (min)"],
                     [k["active_trains"], k["delayed_trains"], k["conflicts"], k["avg_delay_min"]]],
                    [W / 4] * 4, st=st)]
    plan = d["plan"]
    if plan.get("applied"):
        story.append(p(f"Accepted plan in force: {plan['applied']}"
                       + (f" (stale: {', '.join(plan['new_events'])} became known after it)" if plan["stale"] else ""),
                       "body", st))

    story.append(p("Events", "h1", st))
    if d["events"]:
        story.append(table([["Event", "Type", "Train", "Location", "Start", "Duration (min)", "Known from"]] +
                           [[e["event_id"], e["event_type"], e.get("train_id") or "", e["location"], e["start_time"],
                             e["duration_min"], e.get("known_from", "")] for e in d["events"]],
                           [W * x for x in (0.08, 0.2, 0.1, 0.14, 0.1, 0.14, 0.24)], st=st))
    else:
        story.append(p("No events posted.", "body", st))

    story.append(p(f"Conflicts at {m['at']}", "h1", st))
    if d["conflicts"]:
        story.append(table([["Severity", "Type", "Section", "Trains", "Planned entry", "Free from", "Short (min)",
                             "In (min)", "Certainty"]] +
                           [[c["severity"], c["conflict_type"], c["section_id"],
                             " / ".join(x for x in (c["earlier_train"], c["later_train"]) if x),
                             c["window_start"], c["window_end"], c["minutes_short"], c["time_to_conflict_min"],
                             c["certainty"]] for c in d["conflicts"]],
                           [W * x for x in (0.1, 0.1, 0.12, 0.14, 0.1, 0.1, 0.09, 0.08, 0.17)], st=st))
        for c in d["conflicts"]:
            story.append(p(f"{c['section_id']}, {c['later_train']}: " + reason_text(c), "small", st))
    else:
        story.append(p("No conflict is detected from the known events at this time.", "body", st))
    if d["ml_watchlist"]:
        story.append(p("ML watchlist", "h2", st))
        story.append(table([["Train", "Section", "Model score", "Threshold", "Resolved by plan", "Reduced by plan"]] +
                           [[w["train_id"], w["section_id"], w["conflict_probability"], w["threshold"],
                             "yes" if w["resolved_by_plan"] else "no", "yes" if w["reduced_by_plan"] else "no"]
                            for w in d["ml_watchlist"]], [W / 6] * 6, st=st))
    if d["ml_note"]:
        story.append(p(f"Model note: {d['ml_note']}", "small", st))

    story += [PageBreak(), p("Time-distance chart", "h1", st),
              p("Timetable (dashed grey) and what happens (solid: every posted event plus the accepted plan), "
                "from /api/timeline.", "small", st),
              figure(charts.timeline_chart(d["_timeline"], d["_trains"], _min(m["at"])), W)]

    story.append(p("Per-train delays", "h1", st))
    story.append(table([["Train", "Type", "Priority", f"Status at {m['at']}", f"Delay at {m['at']} (min)",
                         "Final arrival", "Final delay (min)", "Wait (min)", "Standing still (min)"]] +
                       [[t["train_id"], t["train_type"], t["priority"], t["status"], t["delay_at_clock_min"],
                         t["final_arrival"] or "", "" if t["final_delay_min"] is None else t["final_delay_min"],
                         t["wait_min"], t["standing_still_min"]] for t in d["per_train"]],
                       [W * x for x in (0.1, 0.12, 0.08, 0.14, 0.12, 0.11, 0.11, 0.1, 0.12)], st=st))

    story.append(p(f"Alert history up to {m['at']}", "h1", st))
    if d["alert_history"]:
        story.append(table([["Alert", "Category", "Appeared", "Cause", "Cleared", "Cause"]] +
                           [[h["title"], h["category"], h["appeared"], h["appeared_cause"]["text"], h["cleared"] or "active",
                             (h["cleared_cause"] or {}).get("text", "")] for h in d["alert_history"]],
                           [W * x for x in (0.2, 0.11, 0.08, 0.25, 0.08, 0.28)], st=st))
    else:
        story.append(p("No alert was raised up to this time.", "body", st))
    story.append(p("Recommendations", "h1", st))
    if not d["recommendations"]:
        story.append(p("No recommendation was computed in this scenario.", "body", st))
    for r in d["recommendations"]:
        head = (f"{r['recommendation_id']}: {r['strategy']} (computed at {_hhmm(r['at_min'])}, "
                f"decision: {r['decision'] or 'pending'})")
        story.append(p(head, "h2", st))
        for line in (r["plain_text"] or "No explanation text stored.").splitlines():
            if line.strip():
                story.append(p(line, "cell", st))
    story.append(p("Decisions", "h1", st))
    if d["decisions"]:
        story.append(table([["Recommendation", "Decision", "Strategy", "Sim time", "By", "Logged (UTC)", "Replaces"]] +
                           [[x["recommendation_id"], x["decision"], x["strategy"], _hhmm(x["at"]),
                             x.get("decided_by") or "", x["logged_at_utc"], x.get("replaces") or ""]
                            for x in d["decisions"]],
                           [W * v for v in (0.15, 0.09, 0.12, 0.08, 0.23, 0.25, 0.08)], st=st))
    else:
        story.append(p("No decision taken.", "body", st))
    meta = f"version {m['scenario_version']} · sim {m['at']} · generated {m['generated_at_utc']} by {m['generated_by']}"
    return build(story, title="RailOpt AI - scenario report", label=m["data_label"], meta=meta)


def _min(hhmm: str) -> int:
    h, mm = hhmm.split(":")
    return int(h) * 60 + int(mm)
