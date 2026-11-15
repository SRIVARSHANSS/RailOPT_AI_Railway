"""API routes (thin layer: all logic lives in app/services). All data SIMULATED."""
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
    EventRequest,
    Health,
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
from app.services import live
from app.services.conflicts import detect_conflicts, project_plan
from app.services.network import RailNetwork, format_time, parse_time

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
             "is_junction": s.is_junction} for s in sorted(net.stations.values(), key=lambda s: s.km_from_start)]


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
    return Health(timetable=store.timetable)


@router.get("/network", response_model=NetworkOut)
def network(timetable: Timetable = "reference", store: ScenarioStore = Depends(get_store)):
    net = store.network(timetable)
    return NetworkOut(
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
    store.reset(req.timetable)
    return scenario(at=None, store=store)


@router.get("/scenario", response_model=ScenarioOut)
def scenario(at: str | None = Query(None, pattern=HHMM, description="clock for the stale-plan check; omit = all posted events"),
             store: ScenarioStore = Depends(get_store)):
    return ScenarioOut(
        timetable=store.timetable,
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
    return EventCreated(event=_event_out(event), events=[_event_out(e) for e in store.events])


@router.get("/state", response_model=StateOut)
def state(at: str = AtQuery, store: ScenarioStore = Depends(get_store)):
    t, net = _clock(at), store.network()
    known = store.known_events(t)
    states = live.train_states(net, store.actual(), t, store.events)   # movement: every posted event
    plan = project_plan(net, t, known, store.route_overrides, store.holds)   # known events + accepted plan
    n_conflicts = len(detect_conflicts(net, plan))
    return StateOut(at=at, known_events=[e.event_id for e in known], trains=states,
                    kpis=live.kpis(states, n_conflicts), plan=store.plan_status(t))


@router.get("/conflicts", response_model=ConflictsOut)
def conflicts(at: str = AtQuery, store: ScenarioStore = Depends(get_store),
              predictor=Depends(get_predictor_or_none)):
    t, net = _clock(at), store.network()
    known = store.known_events(t)
    view = live.conflicts_view(net, t, known, predictor, store.route_overrides, store.holds,
                               store.previous_overrides, store.previous_holds)
    return ConflictsOut(at=at, known_events=[e.event_id for e in known], conflicts=view["conflicts"],
                        ml_watchlist=view["ml_watchlist"], ml_note=view["ml_note"])


@router.post("/optimize", response_model=OptimizeOut)
def optimize(req: OptimizeRequest, store: ScenarioStore = Depends(get_store)):
    t, net = _clock(req.at), store.network()
    known = store.known_events(t)
    # re-plan from the CURRENT state: the accepted plan (if any) shapes history
    view = live.optimize_view(net, t, known, store.holds, store.route_overrides)
    rec_out = None
    rec = view["recommendation"]
    if rec is not None:
        holds, overrides = rec.pop("_holds"), rec.pop("_route_overrides")
        stored = store.add_recommendation(t, rec["strategy"], holds, overrides, rec,
                                          known_event_ids=[e.event_id for e in known])
        rec_out = {"recommendation_id": stored.rec_id, **rec}
    return OptimizeOut(at=req.at, known_events=[e.event_id for e in known],
                       results=view["results"], recommendation=rec_out,
                       replanning_from=store.applied_recommendation)


@router.post("/whatif", response_model=WhatIfOut)
def whatif(req: WhatIfRequest, store: ScenarioStore = Depends(get_store),
           predictor=Depends(get_predictor_or_none)):
    """HYPOTHETICAL: apply events to a COPY of the scenario (events + accepted plan) and
    compare it with the current one. The live store is never touched."""
    t, net = _clock(req.at), store.network()
    copy = store.copy_for_whatif()
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
        cv = live.conflicts_view(net, t, known, predictor, scn.route_overrides, scn.holds,
                                 scn.previous_overrides, scn.previous_holds)
        ov = live.optimize_view(net, t, known, scn.holds, scn.route_overrides)
        rec = ov["recommendation"]
        if rec is not None:
            rec = {k: v for k, v in rec.items() if not k.startswith("_")}
        return {"known_events": [e.event_id for e in known], "conflicts": cv["conflicts"],
                "ml_watchlist": cv["ml_watchlist"], "ml_note": cv["ml_note"],
                "results": ov["results"], "recommendation": rec}

    current_known = store.known_events(t)
    hypothetical_known = current_known + added          # hypothetical events count as known at `at`
    return WhatIfOut(at=req.at, hypothetical_events=[_event_out(e) for e in added],
                     current=side(store, current_known), hypothetical=side(copy, hypothetical_known))


@router.post("/recommendation/{rec_id}/decision", response_model=DecisionOut)
def decide(rec_id: str, req: DecisionRequest, store: ScenarioStore = Depends(get_store)):
    try:
        store.decide(rec_id, req.decision)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown recommendation {rec_id}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return DecisionOut(recommendation_id=rec_id, decision=req.decision,
                       applied_recommendation=store.applied_recommendation, decision_log=store.decision_log)


@router.get("/timeline", response_model=TimelineOut)
def timeline(store: ScenarioStore = Depends(get_store)):
    net = store.network()
    return TimelineOut(timetable=store.timetable, stations=_stations(net),
                       planned=live.planned_timeline(net), actual=live.timeline_rows(net, store.actual()),
                       applied_recommendation=store.applied_recommendation)
