// Shapes of the RailOpt API responses (backend/app/schemas/api.py). All SIMULATED.
type Labelled = { data_label: 'SIMULATED' }

export type Timetable = 'reference' | 'full_day'
export type EventType = 'STOPPAGE' | 'DELAY' | 'TRACK_UNAVAILABLE' | 'PLATFORM_UNAVAILABLE'

export type Station = { code: string; name: string; km: number; platforms: number; is_junction: boolean }
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
export type Scenario = Labelled & {
  timetable: Timetable
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
}
export type Kpis = { active_trains: number; delayed_trains: number; conflicts: number; avg_delay_min: number }
export type StateAt = Labelled & { at: string; known_events: string[]; trains: TrainState[]; kpis: Kpis; plan: PlanStatus }

export type Driver = { feature: string; value: unknown; shap: number; direction: 'raises' | 'lowers' }
export type Prediction = { conflict_probability: number; flagged: boolean; threshold: number; top_drivers: Driver[] }
export type Conflict = {
  conflict_id: string; section_id: string; earlier_train: string | null; later_train: string
  conflict_type: 'OVERLAP' | 'HEADWAY' | 'CLOSURE'; window_start: string; window_end: string
  minutes_short: number; time_to_conflict_min: number; severity: 'CRITICAL' | 'WARNING'
  event_id: string | null; prediction: Prediction | null
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
export type Explanation = {
  reason: string; counterfactual: string; expected_impact: string; solver: string
  delta_total_delay_min: number; delta_weighted_delay: number; note: string
}
export type Recommendation = {
  recommendation_id: string; strategy: string; status: string; actions: string[]
  weighted_delay: number; total_delay: number; delays: Record<string, number>; explanation: Explanation
}
export type OptimizeResult = Labelled & { at: string; known_events: string[]; results: StrategyRow[]; recommendation: Recommendation | null; replanning_from: string | null }

export type WhatIfRecommendation = Omit<Recommendation, 'recommendation_id'>
export type WhatIfSide = {
  known_events: string[]; conflicts: Conflict[]; ml_watchlist: WatchItem[]; ml_note: string | null
  results: StrategyRow[]; recommendation: WhatIfRecommendation | null
}
export type WhatIfResult = Labelled & {
  scenario_label: 'HYPOTHETICAL'; at: string; hypothetical_events: ScenarioEvent[]
  current: WhatIfSide; hypothetical: WhatIfSide; note: string
}
export type DecisionResult = Labelled & { recommendation_id: string; decision: string; applied_recommendation: string | null; decision_log: DecisionLogEntry[] }
