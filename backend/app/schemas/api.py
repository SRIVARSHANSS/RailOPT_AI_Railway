"""Pydantic request / response models. Every response carries data_label = SIMULATED."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
Timetable = Literal["reference", "full_day"]
EventType = Literal["STOPPAGE", "DELAY", "TRACK_UNAVAILABLE", "PLATFORM_UNAVAILABLE"]


class Labelled(BaseModel):
    data_label: Literal["SIMULATED"] = "SIMULATED"


VERSION_DOC = ("'<server boot id>-<revision>': changes on every API start, reset, event and decision; "
               "clients drop cached optimizer results when it differs")


# ---- requests ------------------------------------------------------------------------
class ResetRequest(BaseModel):
    timetable: Timetable = "reference"


class EventRequest(BaseModel):
    event_type: EventType
    train_id: str | None = None
    location: str = Field(description="section_id (STOPPAGE, TRACK_UNAVAILABLE) or station code (DELAY)")
    start_time: str = Field(pattern=HHMM, examples=["10:03"])
    duration_min: int = Field(ge=1, le=600)


class OptimizeRequest(BaseModel):
    at: str = Field(pattern=HHMM, examples=["10:03"])


class WhatIfRequest(BaseModel):
    at: str = Field(pattern=HHMM, examples=["10:20"])
    events: list[EventRequest] = Field(min_length=1, max_length=3,
                                       description="hypothetical events, all treated as known at `at`")


class DecisionRequest(BaseModel):
    decision: Literal["accept", "reject"]


# ---- responses --------------------------------------------------------------------------
class Health(Labelled):
    status: str = "ok"
    timetable: str


class StationOut(BaseModel):
    code: str
    name: str
    km: float
    platforms: int
    is_junction: bool


class SectionOut(BaseModel):
    section_id: str
    from_station: str
    to_station: str
    length_km: float
    tracks: int
    min_run_min: int
    min_headway_min: int
    status: str


class TrainOut(BaseModel):
    train_id: str
    train_no: str
    name: str
    train_type: str
    priority: int


class StopOut(BaseModel):
    train_id: str
    station: str
    seq: int
    sched_arr: str | None
    sched_dep: str | None


class NetworkOut(Labelled):
    timetable: str
    stations: list[StationOut]
    sections: list[SectionOut]
    trains: list[TrainOut]
    schedule: list[StopOut]


class EventOut(BaseModel):
    event_id: str
    event_type: str
    train_id: str | None
    location: str
    start_time: str
    duration_min: int
    known_from: str = Field(description="'posting' for planned closures, else the start time")


class EventCreated(Labelled):
    event: EventOut
    events: list[EventOut]


class PlanStatus(BaseModel):
    applied: str | None = Field(description="accepted recommendation in force, if any")
    stale: bool = Field(description="an event is known now that the accepted plan did not know")
    new_events: list[str]
    basis_at: int | None = Field(description="clock time (minutes) the accepted plan was computed for")


class ScenarioOut(Labelled):
    scenario_version: str = Field(description=VERSION_DOC)
    timetable: str
    events: list[EventOut]
    applied_recommendation: str | None
    plan: PlanStatus
    holds: list[dict[str, Any]]
    route_overrides: list[dict[str, Any]]
    decision_log: list[dict[str, Any]]


class TrainState(BaseModel):
    train_id: str
    train_type: str
    priority: int
    status: Literal["not_started", "at_station", "waiting_at_signal", "in_section", "arrived"]
    location: str
    progress: float | None
    next_station: str | None
    current_delay_min: int
    stopped: bool = Field(False, description="standing still inside the section during a stoppage")


class Kpis(BaseModel):
    active_trains: int
    delayed_trains: int
    conflicts: int
    avg_delay_min: float


class StateOut(Labelled):
    scenario_version: str = Field(description=VERSION_DOC)
    at: str
    known_events: list[str]
    trains: list[TrainState]
    kpis: Kpis
    plan: PlanStatus


class Driver(BaseModel):
    feature: str
    value: Any
    shap: float
    direction: Literal["raises", "lowers"]


class Prediction(BaseModel):
    conflict_probability: float
    flagged: bool
    threshold: float
    top_drivers: list[Driver]


class ConflictOut(BaseModel):
    conflict_id: str
    section_id: str
    earlier_train: str | None
    later_train: str
    conflict_type: str
    window_start: str
    window_end: str
    minutes_short: int
    time_to_conflict_min: int
    severity: Literal["CRITICAL", "WARNING"]
    event_id: str | None
    prediction: Prediction | None


class WatchItem(Prediction):
    train_id: str
    section_id: str
    time_to_section_min: int
    resolved_by_plan: bool = Field(
        False, description="an accepted plan is in force and, in its deterministic replay on the known "
                           "events, this train does not wait before this trip (UI: 'Risk resolved by accepted plan')")
    plan_wait_min: int | None = Field(None, description="wait before this trip in that replay; null without a plan")
    reduced_by_plan: bool = Field(
        False, description="the accepted plan lowers this train's wait before the trip, but not to zero "
                           "(UI: 'Risk reduced by plan (baseline -> plan min wait)')")
    baseline_wait_min: int | None = Field(None, description="wait in a replay of the plan the current one replaced (no plan if none)")


class ConflictsOut(Labelled):
    at: str
    known_events: list[str]
    conflicts: list[ConflictOut]
    ml_watchlist: list[WatchItem] = Field(description="trains the model flags but the rules do not")
    ml_note: str | None


class StrategyRow(BaseModel):
    name: str
    kind: Literal["baseline", "strategy"]
    status: str
    solve_seconds: float | None
    message: str
    weighted_delay: int | None
    total_delay: int | None
    delays: dict[str, int]
    throughput_trains_per_hour: float | None
    violations: int | None
    actions: list[str]


class Explanation(BaseModel):
    reason: str
    counterfactual: str
    expected_impact: str
    solver: str
    delta_total_delay_min: int
    delta_weighted_delay: int
    note: str


class RecommendationBase(BaseModel):
    strategy: str
    status: str
    actions: list[str]
    weighted_delay: int
    total_delay: int
    delays: dict[str, int]
    explanation: Explanation


class RecommendationOut(RecommendationBase):
    recommendation_id: str


class OptimizeOut(Labelled):
    scenario_version: str = Field(description="version this run was computed against")
    at: str
    known_events: list[str]
    results: list[StrategyRow]
    recommendation: RecommendationOut | None
    replanning_from: str | None = Field(None, description="accepted plan this run re-plans on top of")


class WhatIfSide(BaseModel):
    known_events: list[str]
    conflicts: list[ConflictOut]
    ml_watchlist: list[WatchItem]
    ml_note: str | None
    results: list[StrategyRow]
    recommendation: RecommendationBase | None = Field(description="not stored: a what-if cannot be accepted")


class WhatIfOut(Labelled):
    scenario_label: Literal["HYPOTHETICAL"] = "HYPOTHETICAL"
    at: str
    hypothetical_events: list[EventOut]
    current: WhatIfSide
    hypothetical: WhatIfSide
    note: str = "HYPOTHETICAL and SIMULATED: computed on a copy; the live scenario is unchanged."


class DecisionOut(Labelled):
    scenario_version: str = Field(description="version after this decision")
    recommendation_id: str
    decision: str
    applied_recommendation: str | None
    decision_log: list[dict[str, Any]]


class TimelineRow(BaseModel):
    train_id: str
    section_id: str
    from_station: str
    to_station: str
    from_km: float
    to_km: float
    entry_min: int
    exit_min: int
    entry: str
    exit: str
    wait_min: int = Field(description="minutes held at the signal before entering")
    stopped_min: int
    stops: list[StopWindow] = Field(default_factory=list, description="stood still inside the section")
    delay_min: int | None = Field(None, description="exit vs timetabled arrival at to_station")
    alternate: bool = Field(False, description="ran on a standby (alternate) line")


class StopWindow(BaseModel):
    start_min: int
    end_min: int


class ClosureBlock(BaseModel):
    event_id: str
    section_id: str
    from_km: float
    to_km: float
    start_min: int
    end_min: int
    start: str
    end: str


class TimelineOut(Labelled):
    timetable: str
    stations: list[StationOut]
    planned: list[TimelineRow]
    actual: list[TimelineRow] = Field(description="every posted event + the accepted plan")
    before_plan: list[TimelineRow] | None = Field(
        None, description="same events under the plan the accepted one replaced (no plan if none); null without a plan")
    closures: list[ClosureBlock] = Field(default_factory=list)
    applied_recommendation: str | None
    previous_plan: str | None = Field(None, description="plan the accepted one replaced (before_plan basis)")
