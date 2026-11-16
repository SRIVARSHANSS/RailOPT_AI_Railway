"""Pydantic request / response models. Every response carries a data_label: SIMULATED (sample
corridor), REAL (a recorded day replayed unchanged) or "HYPOTHETICAL on a real recorded day"."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# a REAL replay day can run past midnight ('24:35' = 00:35 the next day), up to 47:59
HHMM = r"^([0-3]\d|4[0-7]):[0-5]\d$"
DATE = r"^\d{4}-\d{2}-\d{2}$"
Timetable = Literal["reference", "full_day", "dg_mdu"]
DataLabel = Literal["SIMULATED", "REAL", "HYPOTHETICAL on a real recorded day"]
EventType = Literal["STOPPAGE", "DELAY", "TRACK_UNAVAILABLE", "PLATFORM_UNAVAILABLE"]


class Labelled(BaseModel):
    data_label: DataLabel = "SIMULATED"


VERSION_DOC = ("'<server boot id>-<revision>': changes on every API start, reset, event and decision; "
               "clients drop cached optimizer results when it differs")


# ---- requests ------------------------------------------------------------------------
class ResetRequest(BaseModel):
    timetable: Timetable = "reference"
    mode: Literal["live", "replay"] = Field("live", description="replay = one REAL recorded day (timetable dg_mdu)")
    date: str | None = Field(None, pattern=DATE, examples=["2024-09-12"], description="recorded DG date for replay")


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
    loops: int | None = Field(None, description="loop lines (REAL corridor, ASSUMED); null = not modelled")


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


class ReplayInfo(BaseModel):
    date: str
    weekday: str
    header: str = Field(description="REAL RECORDED MOVEMENTS - <date> - source")
    source: str
    window_start: int
    window_end: int
    trains: int
    divergence: str | None = Field(description="first minute the hypothetical differs from the recording; null = unchanged")
    recorded_overtakes: list[dict[str, Any]]
    placed_waits: list[dict[str, Any]] = Field(description="INTERPOLATED waits placed so the movement fits the model")
    unreliable: list[dict[str, Any]]
    unresolved: list[str]
    flagged_mdu: list[str]
    notes: list[str]


class ScenarioOut(Labelled):
    scenario_version: str = Field(description=VERSION_DOC)
    timetable: str
    mode: Literal["live", "replay"] = "live"
    replay: ReplayInfo | None = None
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
    interpolated: bool = Field(False, description="REAL replay: the position comes from interpolated times")


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
    text: str = Field("", description="plain words for the feature value (template, Phase 7)")
    sentence: str = Field("", description="'Model risk raised by: ...' / 'Model risk lowered by: ...' - "
                                          "explains the model's score, not a physical cause")
    context: dict[str, Any] = Field(default_factory=dict, description="network values the text uses, e.g. section_tracks")


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
    certainty: Literal["FIRM", "ESTIMATED"] = Field(
        "FIRM", description="REAL replay: ESTIMATED = depends on interpolated/estimated times (uncertain, not an alert)")


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


class ConflictRef(BaseModel):
    conflict_id: str
    section_id: str
    earlier_train: str | None
    later_train: str
    conflict_type: str
    window_start: str
    window_end: str
    minutes_short: int
    time_to_conflict_min: int
    severity: str
    event_id: str | None


class PerTrain(BaseModel):
    train_id: str
    without_min: int
    with_min: int
    change_min: int
    text: str


class WhyNot(BaseModel):
    name: str
    kind: Literal["baseline", "strategy", "unavailable"]
    status: str
    weighted_delay: int | None
    total_delay: int | None
    diff_weighted: int | None = Field(description="its weighted delay minus the recommended one")
    actions_count: int | None
    best_actions_count: int | None
    violations: int | None
    text: str


class Constraints(BaseModel):
    respected: bool
    violations: int
    summary: str
    items: list[str]


class AssumptionUsed(BaseModel):
    name: str
    label: Literal["ASSUMED", "CALIBRATED"]
    item: int = Field(description="item number in docs/ASSUMPTIONS.md")
    value: Any
    text: str


class Explanation(BaseModel):
    """Phase 7: every sentence is a template filled from numbers in this payload (no LLM)."""
    reason: str = Field(description="rule-based detector: the interval clash")
    conflict: ConflictRef | None = None
    recommend: str = ""
    counterfactual: str
    expected_impact: str
    per_train: list[PerTrain] = Field(default_factory=list)
    why_not: list[WhyNot] = Field(default_factory=list)
    constraints: Constraints | None = None
    assumptions: list[AssumptionUsed] = Field(default_factory=list)
    solver: str
    confidence: str = Field("", description="CP-SAT status (+ headway sensitivity on REAL replay days)")
    delta_total_delay_min: int
    delta_weighted_delay: int
    note: str
    plain_text: str | None = Field(None, description="whole explanation as plain text (Copy explanation)")


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


class Unavailable(BaseModel):
    name: str
    reason: str


class OptimizeOut(Labelled):
    scenario_version: str = Field(description="version this run was computed against")
    at: str
    known_events: list[str]
    results: list[StrategyRow]
    recommendation: RecommendationOut | None
    replanning_from: str | None = Field(None, description="accepted plan this run re-plans on top of")
    unavailable: list[Unavailable] = Field(default_factory=list, description="strategies not offered here, and why")
    sensitivity: dict[str, Any] | None = Field(None, description="REAL replay: the same run with the other headway")
    notes: list[str] = Field(default_factory=list)


class WhatIfSide(BaseModel):
    known_events: list[str]
    conflicts: list[ConflictOut]
    ml_watchlist: list[WatchItem]
    ml_note: str | None
    results: list[StrategyRow]
    recommendation: RecommendationBase | None = Field(description="not stored: a what-if cannot be accepted")
    unavailable: list[Unavailable] = Field(default_factory=list)


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
    interpolated: bool = Field(False, description="REAL replay: entry or exit time interpolated")


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


# ---- stored results (Analytics, Model Insights): read-only --------------------------------
ResultStatus = Literal["ok", "outdated", "missing"]


class EvaluationOut(Labelled):
    status: ResultStatus = Field(description="outdated = the results CSV or model files changed since the run")
    reasons: list[str]
    command: str = Field(description="command that regenerates the results")
    summary: dict[str, Any] | None = Field(description="eval/reports/eval_summary.json as written by the run")
    distribution: dict[str, Any] | None = Field(description="per-scenario reduction vs no re-planning, summarised from eval_results.csv")
    conclusion: dict[str, Any] | None = Field(description="plain ML-integration finding, derived from the summary")
    solver_totals: dict[str, Any] | None


class ModelOut(Labelled):
    status: ResultStatus
    reasons: list[str]
    command: str
    metrics: dict[str, Any] | None = Field(description="ml/reports/metrics.json as written by training")
    feature_importance: list[dict[str, Any]]
    dataset_check: str | None
    evaluation: dict[str, Any] | None = Field(description="Phase 10/10b finding about ML risk in the optimizer")
