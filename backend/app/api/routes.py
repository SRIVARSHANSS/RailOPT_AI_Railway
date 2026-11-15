"""API routes (thin layer: all logic lives in app/services).

Data label per response: SIMULATED (sample corridor), REAL (a recorded day, unchanged) or
"HYPOTHETICAL on a real recorded day" (anything simulated or decided on top of a replay)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.store import PLANNED_EVENT_TYPES, ScenarioStore, get_store
from app.schemas.api import (
    HHMM,
    ConflictsOut,
    DecisionOut,
    DecisionRequest,
    EventCreated,
    EventOut,
    EvaluationOut,
    EventRequest,
    Health,
    ModelOut,
    NetworkOut,
    OptimizeOut,
    OptimizeRequest,
    ResetRequest,
    ScenarioOut,
    StateOut,
    WhatIfOut,
    WhatIfRequest,
    Timetable,
    TimelineOut,
)
from app.services import live, results
from app.services.conflicts import detect_conflicts, project_plan
from app.services.network import RailNetwork, format_time, parse_time
from app.services.simulator import simulate

router = APIRouter(prefix="/api")


def get_predictor_or_none():
    """The trained predictor, or None if the model files are missing."""
    try:
        from app.services.predictor import get_predictor
        return get_predictor()
    except (FileNotFoundError, OSError):
        return None


# ---- helpers ------------------------------------------------------------------------------
def _event_out(e) -> EventOut:
    return EventOut(event_id=e.event_id, event_type=e.event_type, train_id=e.train_id, location=e.location,
                    start_time=format_time(e.start), duration_min=e.duration,
                    known_from="posting" if e.event_type in PLANNED_EVENT_TYPES else format_time(e.start))


def _stations(net: RailNetwork) -> list[dict]:
    return [{"code": s.code, "name": s.name, "km": s.km_from_start, "platforms": s.platforms,
             "is_junction": s.is_junction, "loops": s.loops}
            for s in sorted(net.stations.values(), key=lambda s: s.km_from_start)]


REAL_ML_NOTE = ("The ML models were trained on the SIMULATED sample corridor only and are not applied to "
                "REAL data (see the real-data model card for delay prediction on this corridor).")
SENSITIVITY_HEADWAY = 4


def _estimated(store: ScenarioStore):
    return store.day.estimated if store.is_replay else None


def _validate_event(net: RailNetwork, req: EventRequest) -> None:
    def bad(msg):
        raise HTTPException(status_code=422, detail=msg)

    needs_train = req.event_type in ("STOPPAGE", "DELAY")
    if needs_train and not req.train_id:
        bad(f"{req.event_type} needs a train_id")
    if req.train_id and req.train_id not in net.trains:
        bad(f"unknown train {req.train_id} in this timetable; known: {sorted(net.trains)}")
    if req.event_type in ("STOPPAGE", "TRACK_UNAVAILABLE"):
        if req.location not in net.sections:
            bad(f"{req.event_type} location must be a section; known: {sorted(net.sections)}")
        if req.event_type == "STOPPAGE":
            sec = net.sections[req.location]
            route = {(s.station) for s in net.schedules[req.train_id]}
            if not {sec.from_station, sec.to_station} <= route:
                bad(f"{req.train_id} does not run over {req.location}")
    elif req.event_type == "DELAY":
        stations = [s.station for s in net.schedules[req.train_id][:-1]]
        if req.location not in stations:
            bad(f"DELAY location must be a station {req.train_id} departs from: {stations}")
    elif req.location not in net.stations:
        bad(f"PLATFORM_UNAVAILABLE location must be a station; known: {sorted(net.stations)}")


def _check_closure(store: ScenarioStore, req: EventRequest) -> None:
    """Reject a closure that would start while a train is inside the section (per the
    scenario's current timeline, accepted plan included)."""
    if req.event_type != "TRACK_UNAVAILABLE":
        return
    msg = live.closure_conflict(store.actual(), req.location, parse_time(req.start_time))
    if msg:
        raise HTTPException(status_code=422, detail=msg)


def _clock(at: str) -> int:
    return parse_time(at)


AtQuery = Query(pattern=HHMM, examples=["10:03"], description="clock time HH:MM")


# ---- routes -------------------------------------------------------------------------------
@router.get("/health", response_model=Health)
def health(store: ScenarioStore = Depends(get_store)):
    return Health(timetable=store.timetable, data_label=store.label())


@router.get("/replay/days")
def replay_days():
    """REAL recorded days of the DG -> MDU corridor and whether each replays exactly."""
    from app.services.realdata.replay import DEMO_DAY, day_checks
    return {"data_label": "REAL", "demo_day": DEMO_DAY, "days": day_checks()}


@router.get("/network", response_model=NetworkOut)
def network(timetable: Timetable = "reference", store: ScenarioStore = Depends(get_store)):
    if store.is_replay and timetable == store.timetable:
        net = store.day.timetable                     # the recorded day's trains, real timetable
    else:
        net = store.network(timetable)
    return NetworkOut(
        data_label="REAL" if timetable == "dg_mdu" else "SIMULATED",
        timetable=timetable,
        stations=_stations(net),
        sections=[vars(s) for s in net.sections.values()],
        trains=[{"train_id": t.train_id, "train_no": t.train_no, "name": t.name,
                 "train_type": t.train_type, "priority": t.priority} for t in net.trains.values()],
        schedule=[{"train_id": tid, "station": s.station, "seq": s.seq,
                   "sched_arr": format_time(s.sched_arr) if s.sched_arr is not None else None,
                   "sched_dep": format_time(s.sched_dep) if s.sched_dep is not None else None}
                  for tid, stops in net.schedules.items() for s in stops],
    )


@router.post("/scenario/reset", response_model=ScenarioOut)
def reset(req: ResetRequest, store: ScenarioStore = Depends(get_store)):
    try:
        store.reset(req.timetable, req.mode, req.date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return scenario(at=None, store=store)


@router.get("/scenario", response_model=ScenarioOut)
def scenario(at: str | None = Query(None, pattern=HHMM, description="clock for the stale-plan check; omit = all posted events"),
             store: ScenarioStore = Depends(get_store)):
    replay_info = None
    if store.is_replay:
        from app.services.realdata.replay import info
        replay_info = info(store.day, store.divergence())
    return ScenarioOut(
        data_label=store.label(),
        scenario_version=store.version,
        timetable=store.timetable,
        mode=store.mode,
        replay=replay_info,
        events=[_event_out(e) for e in store.events],
        applied_recommendation=store.applied_recommendation,
        plan=store.plan_status(_clock(at) if at else None),
        holds=[{"train_id": t, "section_id": s, "until": format_time(v)} for (t, s), v in store.holds.items()],
        route_overrides=[{"train_id": t, "from_station": a, "section_id": s}
                         for (t, a), s in store.route_overrides.items()],
        decision_log=store.decision_log,
    )


@router.post("/events", response_model=EventCreated, status_code=201)
def add_event(req: EventRequest, store: ScenarioStore = Depends(get_store)):
    net = store.network()
    _validate_event(net, req)
    _check_closure(store, req)
    event = store.add_event(req.event_type, req.train_id, req.location, parse_time(req.start_time), req.duration_min)
    return EventCreated(data_label=store.label(), event=_event_out(event), events=[_event_out(e) for e in store.events])


@router.get("/state", response_model=StateOut)
def state(at: str = AtQuery, store: ScenarioStore = Depends(get_store)):
    t = _clock(at)
    known = store.known_events(t)
    est = _estimated(store)
    # movement: every posted event; in a replay, delays are shown against the real timetable
    shown = store.day.timetable if store.is_replay else store.network()
    states = live.train_states(shown, store.actual(), t, store.events, est)
    net = store.planning_network(t)
    plan = project_plan(net, t, known, store.route_overrides, store.holds)   # known events + accepted plan
    found = detect_conflicts(net, plan)
    n_conflicts = sum(1 for c in found if live.certainty(net, c, est) == "FIRM")
    return StateOut(data_label=store.label(), scenario_version=store.version, at=at,
                    known_events=[e.event_id for e in known], trains=states,
                    kpis=live.kpis(states, n_conflicts), plan=store.plan_status(t))


@router.get("/conflicts", response_model=ConflictsOut)
def conflicts(at: str = AtQuery, store: ScenarioStore = Depends(get_store),
              predictor=Depends(get_predictor_or_none)):
    t = _clock(at)
    net = store.planning_network(t)
    known = store.known_events(t)
    view = live.conflicts_view(net, t, known, None if store.is_replay else predictor, store.route_overrides,
                               store.holds, store.previous_overrides, store.previous_holds,
                               _estimated(store), REAL_ML_NOTE if store.is_replay else None)
    return ConflictsOut(data_label=store.label(), at=at, known_events=[e.event_id for e in known],
                        conflicts=view["conflicts"],
                        ml_watchlist=view["ml_watchlist"], ml_note=view["ml_note"])


@router.post("/optimize", response_model=OptimizeOut)
def optimize(req: OptimizeRequest, store: ScenarioStore = Depends(get_store)):
    t = _clock(req.at)
    net = store.planning_network(t)
    version = store.version
    known = store.known_events(t)
    # re-plan from the CURRENT state: the accepted plan (if any) shapes history
    view = live.optimize_view(net, t, known, store.holds, store.route_overrides)
    sensitivity, notes = None, []
    if store.is_replay:
        from app.services.realdata.replay import with_headway
        alt = live.optimize_view(with_headway(net, SENSITIVITY_HEADWAY), t, known, store.holds, store.route_overrides)
        main_rec = view["recommendation"]["strategy"] if view["recommendation"] else None
        alt_rec = alt["recommendation"]["strategy"] if alt["recommendation"] else None
        sensitivity = {
            "headway_min": net.sections[next(iter(net.sections))].min_headway_min,
            "alt_headway_min": SENSITIVITY_HEADWAY,
            "recommended": main_rec, "alt_recommended": alt_rec,
            "ranking": view["ranking"], "alt_ranking": alt["ranking"],
            "alt_weighted_delay": {r["name"]: r["weighted_delay"] for r in alt["results"]},
            "changed": main_rec != alt_rec or view["ranking"] != alt["ranking"],
        }
        notes = ["HYPOTHETICAL on a real recorded day: delays are minutes added to the expected movement "
                 "(recorded so far, then the timetable with current delays carried forward).",
                 "Priorities ASSUMED: PREMIUM 1, SUPERFAST 2, EXPRESS 3 (objective weights 3/2/1).",
                 REAL_ML_NOTE]
    rec_out = None
    rec = view["recommendation"]
    if rec is not None:
        holds, overrides = rec.pop("_holds"), rec.pop("_route_overrides")
        stored = store.add_recommendation(t, rec["strategy"], holds, overrides, rec,
                                          known_event_ids=[e.event_id for e in known])
        rec_out = {"recommendation_id": stored.rec_id, **rec}
    return OptimizeOut(data_label=store.label(decision=True), scenario_version=version, at=req.at,
                       known_events=[e.event_id for e in known],
                       results=view["results"], recommendation=rec_out,
                       replanning_from=store.applied_recommendation, unavailable=view["unavailable"],
                       sensitivity=sensitivity, notes=notes)


@router.post("/whatif", response_model=WhatIfOut)
def whatif(req: WhatIfRequest, store: ScenarioStore = Depends(get_store),
           predictor=Depends(get_predictor_or_none)):
    """HYPOTHETICAL: apply events to a COPY of the scenario (events + accepted plan) and
    compare it with the current one. The live store is never touched."""
    t, net = _clock(req.at), store.network()
    copy = store.copy_for_whatif()
    est = _estimated(store)
    added = []
    for n, ev in enumerate(req.events, start=1):
        try:
            _validate_event(net, ev)
            _check_closure(copy, ev)
        except HTTPException as exc:
            raise HTTPException(status_code=exc.status_code, detail=f"Hypothetical event {n}: {exc.detail}")
        added.append(copy.add_event(ev.event_type, ev.train_id, ev.location, parse_time(ev.start_time),
                                    ev.duration_min, prefix="H"))

    def side(scn: ScenarioStore, known: list) -> dict:
        pnet = scn.planning_network(t)
        cv = live.conflicts_view(pnet, t, known, None if scn.is_replay else predictor, scn.route_overrides,
                                 scn.holds, scn.previous_overrides, scn.previous_holds, est,
                                 REAL_ML_NOTE if scn.is_replay else None)
        ov = live.optimize_view(pnet, t, known, scn.holds, scn.route_overrides)
        rec = ov["recommendation"]
        if rec is not None:
            rec = {k: v for k, v in rec.items() if not k.startswith("_")}
        return {"known_events": [e.event_id for e in known], "conflicts": cv["conflicts"],
                "ml_watchlist": cv["ml_watchlist"], "ml_note": cv["ml_note"],
                "results": ov["results"], "recommendation": rec, "unavailable": ov["unavailable"]}

    current_known = store.known_events(t)
    hypothetical_known = current_known + added          # hypothetical events count as known at `at`
    return WhatIfOut(data_label=store.label(decision=True), at=req.at, hypothetical_events=[_event_out(e) for e in added],
                     current=side(store, current_known), hypothetical=side(copy, hypothetical_known))


@router.post("/recommendation/{rec_id}/decision", response_model=DecisionOut)
def decide(rec_id: str, req: DecisionRequest, store: ScenarioStore = Depends(get_store)):
    try:
        store.decide(rec_id, req.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown recommendation {rec_id}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return DecisionOut(data_label=store.label(decision=True), scenario_version=store.version,
                       recommendation_id=rec_id, decision=req.decision,
                       applied_recommendation=store.applied_recommendation, decision_log=store.decision_log)


@router.get("/timeline", response_model=TimelineOut)
def timeline(store: ScenarioStore = Depends(get_store)):
    """Time-distance data. `actual` = every posted event + the accepted plan (what happens);
    `before_plan` = the same events under the plan the accepted one replaced (none if it replaced
    nothing); null while no plan is accepted."""
    net = store.network()
    before = None
    if store.is_replay:
        from app.services.realdata.replay import frozen_movement, planned_rows
        day, est = store.day, store.day.estimated
        if store.applied_recommendation is not None:
            prev = simulate(frozen_movement(day, store.divergence() or 0), store.events,
                            route_overrides=store.previous_overrides or None, holds=store.previous_holds or None)
            before = live.timeline_rows(day.timetable, prev, store.events, est)
        planned, actual = planned_rows(day), live.timeline_rows(day.timetable, store.actual(), store.events, est)
    else:
        if store.applied_recommendation is not None:
            replay = simulate(net, store.events, route_overrides=store.previous_overrides or None,
                              holds=store.previous_holds or None)
            before = live.timeline_rows(net, replay, store.events)
        planned, actual = live.planned_timeline(net), live.timeline_rows(net, store.actual(), store.events)
    return TimelineOut(data_label=store.label(), timetable=store.timetable, stations=_stations(net),
                       planned=planned, actual=actual,
                       before_plan=before, closures=live.closure_blocks(net, store.events),
                       applied_recommendation=store.applied_recommendation,
                       previous_plan=next((d["replaces"] for d in reversed(store.decision_log) if d["decision"] == "accept"), None)
                       if store.applied_recommendation else None)


@router.get("/evaluation", response_model=EvaluationOut)
def evaluation():
    """Stored Phase 10/10b evaluation (eval/reports), hash-checked. Nothing is recomputed."""
    return EvaluationOut(**results.evaluation_view())


@router.get("/model", response_model=ModelOut)
def model():
    """Stored ML metrics and SHAP importance (ml/reports), hash-checked against the model files."""
    return ModelOut(**results.model_view())
