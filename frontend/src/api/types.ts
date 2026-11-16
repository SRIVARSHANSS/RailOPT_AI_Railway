// Shapes of the RailOpt API responses (backend/app/schemas/api.py).
// data_label: SIMULATED (sample corridor), REAL (recorded day, unchanged), or HYPOTHETICAL on top of it.
export type DataLabel = 'SIMULATED' | 'REAL' | 'HYPOTHETICAL on a real recorded day'
type Labelled = { data_label: DataLabel }

export type Timetable = 'reference' | 'full_day' | 'dg_mdu' | 'custom'
export type EventType = 'STOPPAGE' | 'DELAY' | 'TRACK_UNAVAILABLE' | 'PLATFORM_UNAVAILABLE'

export type Station = { code: string; name: string; km: number; platforms: number; is_junction: boolean; loops?: number | null }
export type Section = {
  section_id: string; from_station: string; to_station: string; length_km: number
  tracks: number; min_run_min: number; min_headway_min: number; status: string
}
export type Train = { train_id: string; train_no: string; name: string; train_type: string; priority: number }
export type Stop = { train_id: string; station: string; seq: number; sched_arr: string | null; sched_dep: string | null }
export type Network = Labelled & { timetable: Timetable; stations: Station[]; sections: Section[]; trains: Train[]; schedule: Stop[] }

export type ScenarioEvent = {
  event_id: string; event_type: EventType; train_id: string | null; location: string
  start_time: string; duration_min: number; known_from: string
}
export type DecisionLogEntry = { recommendation_id: string; decision: 'accept' | 'reject'; strategy: string; at: number; logged_at_utc: string }
export type PlanStatus = { applied: string | null; stale: boolean; new_events: string[]; basis_at: number | null }
export type ReplayInfo = {
  date: string; weekday: string; header: string; source: string; window_start: number; window_end: number
  trains: number; divergence: string | null
  recorded_overtakes: { overtaking: string; overtaken: string; dg_departures: string[]; mdu_arrivals: string[] }[]
  placed_waits: { train_id: string; kind: string; station: string; wait_min: number; by?: string }[]
  unreliable: { train_id: string; station: string; reason: string }[]
  unresolved: string[]; flagged_mdu: string[]; notes: string[]
}
export type Scenario = Labelled & {
  scenario_version: string
  timetable: Timetable
  mode: 'live' | 'replay'
  replay: ReplayInfo | null
  events: ScenarioEvent[]
  applied_recommendation: string | null
  plan: PlanStatus
  holds: { train_id: string; section_id: string; until: string }[]
  route_overrides: { train_id: string; from_station: string; section_id: string }[]
  decision_log: DecisionLogEntry[]
}

export type TrainStatus = 'not_started' | 'at_station' | 'waiting_at_signal' | 'in_section' | 'arrived'
export type TrainState = {
  train_id: string; train_type: string; priority: number; status: TrainStatus
  location: string; progress: number | null; next_station: string | null; current_delay_min: number
  stopped: boolean
  interpolated?: boolean
}
export type Kpis = { active_trains: number; delayed_trains: number; conflicts: number; avg_delay_min: number }
export type StateAt = Labelled & { scenario_version: string; at: string; known_events: string[]; trains: TrainState[]; kpis: Kpis; plan: PlanStatus }

// text / sentence: API templates explaining the MODEL'S score ('Model risk raised by: ...'), not a cause
export type Driver = { feature: string; value: unknown; shap: number; direction: 'raises' | 'lowers'; text: string; sentence: string; context?: Record<string, unknown> }
export type Prediction = { conflict_probability: number; flagged: boolean; threshold: number; top_drivers: Driver[] }
export type Conflict = {
  conflict_id: string; section_id: string; earlier_train: string | null; later_train: string
  conflict_type: 'OVERLAP' | 'HEADWAY' | 'CLOSURE'; window_start: string; window_end: string
  minutes_short: number; time_to_conflict_min: number; severity: 'CRITICAL' | 'WARNING'
  event_id: string | null; prediction: Prediction | null
  certainty?: 'FIRM' | 'ESTIMATED'
}
export type WatchItem = Prediction & {
  train_id: string; section_id: string; time_to_section_min: number
  resolved_by_plan: boolean; plan_wait_min: number | null
  reduced_by_plan: boolean; baseline_wait_min: number | null
}
export type ConflictsAt = Labelled & { at: string; known_events: string[]; conflicts: Conflict[]; ml_watchlist: WatchItem[]; ml_note: string | null }

export type StrategyRow = {
  name: string; kind: 'baseline' | 'strategy'; status: string; solve_seconds: number | null; message: string
  weighted_delay: number | null; total_delay: number | null; delays: Record<string, number>
  throughput_trains_per_hour: number | null; violations: number | null; actions: string[]
}
export type WhyNot = {
  name: string; kind: 'baseline' | 'strategy' | 'unavailable'; status: string; weighted_delay: number | null
  total_delay: number | null; diff_weighted: number | null; actions_count: number | null
  best_actions_count: number | null; violations: number | null; text: string
}
export type AssumptionUsed = { name: string; label: 'ASSUMED' | 'CALIBRATED'; item: number; value: unknown; text: string }
/** Phase 7: every sentence is an API template filled from numbers in the same payload (no LLM). */
export type Explanation = {
  reason: string; recommend: string; counterfactual: string; expected_impact: string; solver: string
  per_train: { train_id: string; without_min: number; with_min: number; change_min: number; text: string }[]
  why_not: WhyNot[]
  constraints: { respected: boolean; violations: number; summary: string; items: string[] } | null
  assumptions: AssumptionUsed[]
  confidence: string; plain_text: string | null
  delta_total_delay_min: number; delta_weighted_delay: number; note: string
}
export type Recommendation = {
  recommendation_id: string; strategy: string; status: string; actions: string[]
  weighted_delay: number; total_delay: number; delays: Record<string, number>; explanation: Explanation
}
export type Unavailable = { name: string; reason: string }
export type Sensitivity = {
  headway_min: number; alt_headway_min: number; recommended: string | null; alt_recommended: string | null
  ranking: string[]; alt_ranking: string[]; alt_weighted_delay: Record<string, number | null>; changed: boolean
}
export type OptimizeResult = Labelled & {
  scenario_version: string; at: string; known_events: string[]; results: StrategyRow[]
  recommendation: Recommendation | null; replanning_from: string | null
  unavailable?: Unavailable[]; sensitivity?: Sensitivity | null; notes?: string[]
}

export type WhatIfRecommendation = Omit<Recommendation, 'recommendation_id'>
export type WhatIfSide = {
  known_events: string[]; conflicts: Conflict[]; ml_watchlist: WatchItem[]; ml_note: string | null
  results: StrategyRow[]; recommendation: WhatIfRecommendation | null
}
export type WhatIfResult = Labelled & {
  scenario_label: 'HYPOTHETICAL'; at: string; hypothetical_events: ScenarioEvent[]
  current: WhatIfSide; hypothetical: WhatIfSide; note: string
}
export type DecisionResult = Labelled & { scenario_version: string; recommendation_id: string; decision: string; applied_recommendation: string | null; decision_log: DecisionLogEntry[] }

// ---- GET /api/timeline (time-distance chart) ----
export type TimelineRow = {
  train_id: string; section_id: string; from_station: string; to_station: string
  from_km: number; to_km: number; entry_min: number; exit_min: number; entry: string; exit: string
  wait_min: number; stopped_min: number
  stops: { start_min: number; end_min: number }[]
  delay_min: number | null
  alternate: boolean
  interpolated?: boolean
}
export type ClosureBlock = {
  event_id: string; section_id: string; from_km: number; to_km: number
  start_min: number; end_min: number; start: string; end: string
}
export type Timeline = Labelled & {
  timetable: Timetable
  stations: Station[]
  planned: TimelineRow[]
  actual: TimelineRow[]
  before_plan: TimelineRow[] | null
  closures: ClosureBlock[]
  applied_recommendation: string | null
  previous_plan: string | null
}

// ---- GET /api/evaluation, GET /api/model (stored results, read-only) ----
export type ResultStatus = 'ok' | 'outdated' | 'missing'
export type Ci = [number, number]
export type Desc = { mean: number; mean_ci: Ci; median: number; median_ci: Ci }
export type Paired = {
  n: number; wins: number; ties: number; losses: number
  mean_diff: number; mean_diff_ci: Ci; median_diff: number; wilcoxon_p: number; significant: boolean
}
export type EvalSettingName = 'deterministic' | 'robustness'
export type EvalSetting = {
  methods: Record<string, Record<string, Desc>>
  paired_vs_no_replanning: Record<string, Record<string, Paired>>
  ml_ablation: Record<string, Paired>
  dynamic_vs_single_shot: Record<string, Paired>
  variants_vs_dynamic: Record<string, Record<string, Paired>>
}
export type SolverStat = {
  solves: number; optimal: number; feasible: number; other: number; plans_adopted: number
  solve_s_mean: number; solve_s_p95: number; solve_s_max: number
}
export type EvalSummary = {
  label: string
  config: { scenarios: number; seed: number; timetable: string; replays: number; bootstrap: number; closure_notice_min: number; methods: Record<string, string> }
  settings: Record<EvalSettingName, EvalSetting>
  solver: Record<string, SolverStat>
  single_shot_guarantee: { optimal_single_shots: number; worse_on_events_known_at_solve: string[]; worse_on_full_replay: string[]; note: string }
  scenarios: { trains: number; training_runs: number; training_seed: number; overlap_with_training: number | null; disruptions_total: number; per_scenario: Record<string, number>; types: Record<string, number> }
  violations: number
  replays_checked: number
  runtime_s: number
}
export type DistMethod = {
  n: number; mean: number; q1: number; median: number; q3: number; whisker_low: number; whisker_high: number
  min: number; max: number; improved: number; unchanged: number; worse: number; histogram: number[]
}
export type Conclusion = { text: string; variants: string[]; preregistered: string[]; improved: string[]; significantly_worse: string[]; reference: string }
export type SolverTotal = { solves: number; optimal: number; feasible: number; solve_s_mean: number; solve_s_max: number }
export type Evaluation = Labelled & {
  status: ResultStatus; reasons: string[]; command: string
  summary: EvalSummary | null
  distribution: Record<EvalSettingName, { edges: number[]; methods: Record<string, DistMethod> }> | null
  conclusion: Conclusion | null
  solver_totals: { phase10: SolverTotal; variants_10b: SolverTotal } | null
}

export type RegScores = { mae: number; rmse: number; r2: number }
export type ClsScores = { precision: number; recall: number; f1: number; pr_auc: number; threshold: number | null }
export type ModelMetrics = {
  note: string
  data: { rows: number; runs: number; runs_generated: number; split_method: string; split: Record<'train' | 'val' | 'test', { runs: number; rows: number; first_run: string; last_run: string }> }
  seed: number
  delay: { baselines: Record<string, { val: RegScores; test: RegScores }>; models: Record<string, { val: RegScores; test: RegScores }>; best_model: string; selected_by: string }
  conflict: {
    positive_rate: Record<'train' | 'val' | 'test', number>
    baselines: Record<string, { val: ClsScores; test: ClsScores }>
    models: Record<string, { val: ClsScores; test: ClsScores }>
    best_model: string; selected_by: string
    operating_points: {
      'recall_at_least_0.80': { rule: string; threshold: number; val: ClsScores; test: ClsScores }
      equal_to_rule_precision: { rule: string; rule_val_precision: number; rule_val_recall: number; threshold: number; val: ClsScores; test: ClsScores }
    }
    ablation: { model: string; with_rule_flag: Record<string, { threshold: number; val: ClsScores; test: ClsScores }>; without_rule_flag: Record<string, { threshold: number; val: ClsScores; test: ClsScores }> }
  }
  shap_rows: number
  small_data_check: { runs: number; n_iter_per_model: number; best_model: string; rule_val_precision: number; rule_val_recall: number; model_val_recall_at_rule_precision: number }
}
export type ModelResults = Labelled & {
  status: ResultStatus; reasons: string[]; command: string
  metrics: ModelMetrics | null
  feature_importance: { model: 'delay' | 'conflict'; feature: string; mean_abs_shap: number }[]
  dataset_check: string | null
  evaluation: {
    status: ResultStatus
    conclusion: Conclusion | null
    settings: Record<EvalSettingName, { variants_vs_dynamic: Record<string, Record<string, Paired>>; methods: Record<string, Desc> }>
  } | null
}
