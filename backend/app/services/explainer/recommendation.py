"""Template explanation of a recommendation (Phase 7). No LLM, no hand-typed numbers.

Every number in every sentence is taken from a value carried in the same API payload: the
strategy rows, the structured fields next to each sentence (per_train, why_not, assumptions,
conflict), or the network the run used. The word "optimal" appears only when CP-SAT returned
OPTIMAL. The Reason line comes from the rule-based detector (a real interval clash), so it may
say "because"; ML driver sentences never do (drivers.py).
"""
from __future__ import annotations

from app.services.network import RailNetwork, format_time
from app.services.optimizer.config import WEIGHT_BY_PRIORITY

DISCLAIMER = "Decision support only: the controller decides. RailOpt AI controls no trains or signals."
NOTE = "Template text built from the replayed numbers; the controller decides."
TIE_ORDER = ["HOLD", "REROUTE", "RESEQUENCE", "COMBINED"]


# ---------------------------------------------------------------------------
# parts
# ---------------------------------------------------------------------------
def conflict_ref(c) -> dict | None:
    if c is None:
        return None
    return {"conflict_id": c.conflict_id, "section_id": c.section_id, "earlier_train": c.earlier,
            "later_train": c.later, "conflict_type": c.conflict_type,
            "window_start": format_time(c.window_start), "window_end": format_time(c.window_end),
            "minutes_short": c.minutes_short, "time_to_conflict_min": c.time_to_conflict,
            "severity": c.severity, "event_id": c.event_id}


def reason_text(ref: dict | None) -> str:
    if ref is None:
        return "No conflict is detected from the known events at this time."
    if ref["conflict_type"] == "CLOSURE":
        return (f"{ref['later_train']} is planned to enter {ref['section_id']} at {ref['window_start']} "
                f"while it is closed ({ref['event_id']}) until {ref['window_end']}.")
    return (f"{ref['later_train']} is planned to enter {ref['section_id']} at {ref['window_start']}, "
            f"which clashes because {ref['earlier_train']} holds it until {ref['window_end']} "
            f"({ref['conflict_type']}, {ref['minutes_short']} min short, {ref['severity']}, "
            f"in {ref['time_to_conflict_min']} min).")


def _baseline_lead(base) -> str:
    return "Keeping the accepted plan" if base.message.startswith("keeps") else "Without re-planning"


def per_train(best, base) -> list[dict]:
    rows = []
    for t in sorted(set(base.delays) | set(best.delays)):
        a, b = base.delays.get(t, 0), best.delays.get(t, 0)
        if a == b:
            continue
        change = b - a
        rows.append({"train_id": t, "without_min": a, "with_min": b, "change_min": change,
                     "text": f"{t}: {a} -> {b} min late ({'+' if change > 0 else '-'}{abs(change)} min)."})
    return rows


def why_not(best, results, unavailable: list[dict]) -> list[dict]:
    """One line per other strategy row (baselines included) and per strategy not offered."""
    out = []
    for r in results:
        if r.name == best.name:
            continue
        tag = f"{r.name} (baseline)" if r.kind == "baseline" else r.name
        item = {"name": r.name, "kind": r.kind, "status": r.status, "weighted_delay": r.weighted_delay,
                "total_delay": r.total_delay, "diff_weighted": None, "actions_count": len(r.actions),
                "best_actions_count": len(best.actions), "violations": len(r.violations) if r.replay else None}
        if r.weighted_delay is None:
            if r.status == "INFEASIBLE":
                text = f"{tag}: no plan meets the constraints (CP-SAT status INFEASIBLE)."
            else:
                text = f"{tag}: no plan was found within the solver's time limit (CP-SAT status {r.status})."
        else:
            d = r.weighted_delay - best.weighted_delay
            item["diff_weighted"] = d
            if d > 0:
                text = f"{tag}: weighted delay {r.weighted_delay}, {d} more than {best.name}."
            elif d < 0:
                text = (f"{tag}: weighted delay {r.weighted_delay}, {abs(d)} less than {best.name}; "
                        f"baselines are comparisons, the recommendation is the best re-planning strategy.")
            elif r.kind == "baseline":
                text = f"{tag}: weighted delay {r.weighted_delay}, the same as {best.name}."
            elif len(r.actions) > len(best.actions):
                text = (f"{tag}: weighted delay {r.weighted_delay}, the same as {best.name}, but it needs "
                        f"{len(r.actions)} actions instead of {len(best.actions)}.")
            else:
                text = (f"{tag}: weighted delay {r.weighted_delay}, the same as {best.name}; ties go to the "
                        f"simpler strategy in the order {', '.join(TIE_ORDER)}.")
            if r.replay is not None and r.violations:
                text = text[:-1] + f"; its replay breaks {len(r.violations)} constraint(s)."
        item["text"] = text
        out.append(item)
    for u in unavailable:
        out.append({"name": u["name"], "kind": "unavailable", "status": "NOT_OFFERED", "weighted_delay": None,
                    "total_delay": None, "diff_weighted": None, "actions_count": None, "best_actions_count": None,
                    "violations": None, "text": f"{u['name']}: not offered here. {u['reason']}"})
    return out


def constraints(net: RailNetwork, best, known) -> dict:
    """What the replay of the recommended plan was checked against (find_violations)."""
    n = len(best.violations)
    if n:
        return {"respected": False, "violations": n, "items": [],
                "summary": f"The replay of {best.name} breaks {n} constraint(s); see the strategy table."}
    closures = [e for e in known if e.event_type == "TRACK_UNAVAILABLE"]
    items = ["Minimum headway on every section.",
             "Section capacity: no more trains on a section than it has tracks.",
             "Minimum running time on every section.",
             "Track closures: no train uses a section while it is closed"
             + (" (no closure is known)." if not closures else "."),
             "No train leaves a station before its scheduled time."]
    if any(s.loops is not None for s in net.stations.values()):
        items.append("No overtaking without a free loop at the station.")
    if net.frozen_before is not None:
        items.append("Movement before the first hypothetical event is the recording and is not re-checked.")
    return {"respected": True, "violations": 0, "items": items,
            "summary": f"The replay of {best.name} has 0 violations of these checks."}


def assumptions(net: RailNetwork, real: bool) -> list[dict]:
    """The ASSUMED / CALIBRATED values this recommendation depends on, read from the network."""
    heads = {sid: s.min_headway_min for sid, s in net.sections.items() if s.status != "standby"}
    weights = {str(p): w for p, w in WEIGHT_BY_PRIORITY.items()}
    out = []
    if real:
        h = sorted(set(heads.values()))
        out.append({"name": "min_headway_min", "label": "CALIBRATED", "item": 64, "value": h[0] if len(h) == 1 else heads,
                    "text": (f"Minimum headway {h[0]} min on every section (CALIBRATED, ASSUMPTIONS.md item 64): "
                             f"still one train per block section." if len(h) == 1 else
                             "Minimum headway per section: " + ", ".join(f"{k} {v} min" for k, v in heads.items())
                             + " (CALIBRATED, ASSUMPTIONS.md item 64).")})
        loops = {c: s.loops for c, s in net.stations.items() if s.loops is not None}
        out.append({"name": "loops", "label": "ASSUMED", "item": 65, "value": loops,
                    "text": "Loops per station: " + ", ".join(f"{c} {v}" for c, v in loops.items())
                            + " (ASSUMED, ASSUMPTIONS.md item 65)."})
        types = {}
        for t in net.trains.values():
            types.setdefault(t.train_type, t.priority)
        out.append({"name": "priorities", "label": "ASSUMED", "item": 66,
                    "value": {"priority": types, "weight": weights},
                    "text": "Priorities: " + ", ".join(f"{k} {v}" for k, v in sorted(types.items(), key=lambda kv: kv[1]))
                            + "; objective weight by priority " + ", ".join(f"{p} -> {w}" for p, w in weights.items())
                            + " (ASSUMED, ASSUMPTIONS.md item 66)."})
        out.append({"name": "min_run_min", "label": "ASSUMED", "item": 50, "value": None,
                    "text": "Minimum running time from section length at an assumed top speed "
                            "(ASSUMED, ASSUMPTIONS.md item 50)."})
        out.append({"name": "knowledge", "label": "ASSUMED", "item": 70, "value": None,
                    "text": "Planning sees only what is known at the clock time: the recorded movement so far, "
                            "then the timetable with current delays carried forward (ASSUMPTIONS.md item 70)."})
    else:
        out.append({"name": "min_headway_min", "label": "ASSUMED", "item": 1, "value": heads,
                    "text": "Minimum headway per section: " + ", ".join(f"{k} {v} min" for k, v in heads.items())
                            + " (sections.csv, ASSUMPTIONS.md item 1)."})
        out.append({"name": "weights", "label": "ASSUMED", "item": 24, "value": weights,
                    "text": "Objective weight by priority: " + ", ".join(f"{p} -> {w}" for p, w in weights.items())
                            + " (ASSUMPTIONS.md item 24)."})
        out.append({"name": "min_run_min", "label": "ASSUMED", "item": 3, "value": None,
                    "text": "Running times never below each section's minimum running time (ASSUMPTIONS.md item 3)."})
    return out


def confidence(status: str, name: str, sensitivity: dict | None = None) -> str:
    if status == "OPTIMAL":
        text = f"CP-SAT status OPTIMAL: proven optimal for the {name} model."
    else:
        text = (f"CP-SAT status {status}: a valid plan, not proven to be the best within the "
                f"solver's time limit.")
    if sensitivity:
        h, alt = sensitivity["headway_min"], sensitivity["alt_headway_min"]
        alt_rec = sensitivity.get("alt_recommended")
        if alt_rec == sensitivity.get("recommended") and not sensitivity.get("changed"):
            text += f" Same recommendation and ranking at headway {alt} min as at {h} min."
        elif alt_rec == sensitivity.get("recommended"):
            text += (f" Same recommendation at headway {alt} min, but the ranking differs: "
                     f"{' > '.join(sensitivity['alt_ranking'])}.")
        else:
            text += (f" Differs at headway {alt} min: the recommendation there is {alt_rec or 'none'} "
                     f"instead of {sensitivity.get('recommended')}.")
    return text


# ---------------------------------------------------------------------------
# whole explanation
# ---------------------------------------------------------------------------
def explain(net: RailNetwork, best, base, results, conflicts, unavailable: list[dict], known) -> dict:
    # the conflict the plan answers: CRITICAL before WARNING, then the soonest
    ranked = sorted(conflicts, key=lambda c: (c.severity != "CRITICAL", c.time_to_conflict, c.window_start))
    ref = conflict_ref(ranked[0] if ranked else None)
    lead = _baseline_lead(base)
    late = ", ".join(f"{t} {d} min" for t, d in base.delays.items() if d) or "no train late"
    counterfactual = f"{lead}: weighted delay {base.weighted_delay}, total delay {base.total_delay} min ({late})."
    d_total = best.total_delay - base.total_delay
    d_weighted = best.weighted_delay - base.weighted_delay
    if d_weighted < 0:
        impact = (f"{best.name}: weighted delay {best.weighted_delay} ({d_weighted:+d}), "
                  f"total delay {best.total_delay} min ({d_total:+d} min).")
    else:
        impact = f"No strategy improves on {lead.lower()} (weighted delay {best.weighted_delay})."
    real = any(s.loops is not None for s in net.stations.values())
    return {
        "reason": reason_text(ref),
        "conflict": ref,
        "recommend": (f"{best.name}: " + "; ".join(best.actions) + ".") if best.actions
                     else f"{best.name}: no action needed.",
        "counterfactual": counterfactual,
        "expected_impact": impact,
        "per_train": per_train(best, base),
        "why_not": why_not(best, results, unavailable),
        "constraints": constraints(net, best, known),
        "assumptions": assumptions(net, real),
        "solver": confidence(best.status, best.name),
        "confidence": confidence(best.status, best.name),
        "delta_total_delay_min": d_total,
        "delta_weighted_delay": d_weighted,
        "note": NOTE,
        "plain_text": None,
    }


def with_sensitivity(expl: dict, status: str, name: str, sensitivity: dict | None) -> dict:
    """REAL replay: add the headway-sensitivity result to the confidence line."""
    expl["confidence"] = confidence(status, name, sensitivity)
    return expl


def sentences(expl: dict) -> list[str]:
    """Every generated sentence of an explanation, in reading order."""
    out = [expl["reason"], expl["recommend"], expl["counterfactual"], expl["expected_impact"]]
    out += [p["text"] for p in expl.get("per_train", [])]
    out += [w["text"] for w in expl.get("why_not", [])]
    out += [expl["constraints"]["summary"], *expl["constraints"]["items"]] if expl.get("constraints") else []
    out += [a["text"] for a in expl.get("assumptions", [])]
    out += [expl["confidence"]]
    return out


def plain_text(expl: dict, *, title: str, data_label: str, scenario_version: str, at: str) -> str:
    """The whole explanation as plain text (the UI's "Copy explanation" button copies this)."""
    lines = [title, f"Data: {data_label}. Scenario version {scenario_version}, clock {at}.", "",
             f"Reason: {expl['reason']}", f"What we recommend: {expl['recommend']}",
             f"Counterfactual: {expl['counterfactual']}", f"Expected impact: {expl['expected_impact']}"]
    lines += [f"  - {p['text']}" for p in expl["per_train"]]
    lines += ["Why not the others?"] + [f"  - {w['text']}" for w in expl["why_not"]]
    lines += ["Constraints respected:" if expl["constraints"]["respected"] else "Constraints:"]
    lines += [f"  {expl['constraints']['summary']}"] + [f"  - {t}" for t in expl["constraints"]["items"]]
    lines += ["Assumptions this depends on:"] + [f"  - {a['text']}" for a in expl["assumptions"]]
    lines += [f"Confidence: {expl['confidence']}", "", DISCLAIMER]
    return "\n".join(lines)
