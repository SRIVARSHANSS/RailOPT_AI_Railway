// React Query hooks. The UI only displays what the API returns; no railway logic here.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { fmt, toMin } from '../lib/time'
import { useConsole, useSim } from '../store/sim'
import type {
  ConflictsAt, DecisionResult, Evaluation, EventType, ModelResults, Network, OptimizeResult, Scenario, StateAt, Timeline, Timetable, WhatIfResult,
} from './types'

export const qk = {
  scenario: ['scenario'] as const,
  network: (t: Timetable) => ['network', t] as const,
  state: (m: number) => ['state', m] as const,
  conflicts: (m: number) => ['conflicts', m] as const,
  timeline: ['timeline'] as const,
}

export const useScenario = () =>
  useQuery({ queryKey: qk.scenario, queryFn: () => api<Scenario>('/api/scenario'), retry: false })

export const useNetwork = (timetable: Timetable | undefined) =>
  useQuery({
    queryKey: qk.network(timetable ?? 'reference'),
    queryFn: () => api<Network>(`/api/network?timetable=${timetable}`),
    enabled: Boolean(timetable),
    staleTime: Infinity,
  })

export const useStateAt = (minute: number, enabled = true) =>
  useQuery({
    queryKey: qk.state(minute),
    queryFn: () => api<StateAt>(`/api/state?at=${fmt(minute)}`),
    placeholderData: keepPreviousData,
    enabled,
    retry: false,
  })

export const useConflictsAt = (minute: number) =>
  useQuery({
    queryKey: qk.conflicts(minute),
    queryFn: () => api<ConflictsAt>(`/api/conflicts?at=${fmt(minute)}`),
    placeholderData: keepPreviousData,
    retry: false,
  })

export const useTimeline = () =>
  useQuery({ queryKey: qk.timeline, queryFn: () => api<Timeline>('/api/timeline'), retry: false })

/** Stored results (read-only files on the server): fetched once per visit. */
export const useEvaluation = () =>
  useQuery({ queryKey: ['evaluation'], queryFn: () => api<Evaluation>('/api/evaluation'), retry: false, staleTime: 60_000 })

export const useModelResults = () =>
  useQuery({ queryKey: ['model'], queryFn: () => api<ModelResults>('/api/model'), retry: false, staleTime: 60_000 })

/** Anything that changes the scenario invalidates every time-based view. */
function useInvalidateScenario() {
  const qc = useQueryClient()
  return useCallback(() => {
    qc.invalidateQueries({ queryKey: qk.scenario })
    qc.invalidateQueries({ queryKey: ['state'] })
    qc.invalidateQueries({ queryKey: ['conflicts'] })
    qc.invalidateQueries({ queryKey: qk.timeline })
    qc.invalidateQueries({ queryKey: ['health'] })
  }, [qc])
}

export type ResetArgs = { timetable: Timetable; mode?: 'live' | 'replay'; date?: string }

/** REAL recorded days of the DG -> MDU corridor (GET /api/replay/days). */
export const useReplayDays = () =>
  useQuery({
    queryKey: ['replay-days'],
    queryFn: () => api<{ demo_day: string; days: { date: string; weekday: string; trains: number; reproduced_exactly: boolean; recorded_overtakes: number }[] }>('/api/replay/days'),
    staleTime: Infinity,
    retry: false,
  })

export function useResetScenario() {
  const invalidate = useInvalidateScenario()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: ResetArgs) =>
      api<Scenario>('/api/scenario/reset', { method: 'POST', body: JSON.stringify(args) }),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ['network'] }) // a replay day has its own trains
      invalidate()
    },
  })
}

export type NewEvent = { event_type: EventType; train_id: string | null; location: string; start_time: string; duration_min: number }

export function useAddEvent() {
  const invalidate = useInvalidateScenario()
  return useMutation({
    mutationFn: (ev: NewEvent) => api<{ event: { event_id: string; known_from: string } }>('/api/events', { method: 'POST', body: JSON.stringify(ev) }),
    onSuccess: invalidate,
  })
}

export const useOptimize = () =>
  useMutation({
    mutationFn: (minute: number) => api<OptimizeResult>('/api/optimize', { method: 'POST', body: JSON.stringify({ at: fmt(minute) }) }),
  })

export function useDecide() {
  const invalidate = useInvalidateScenario()
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'accept' | 'reject' }) =>
      api<DecisionResult>(`/api/recommendation/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) }),
    onSuccess: (r) => {
      useConsole.getState().adoptVersion(r.scenario_version) // our own decision: keep the cached result
      invalidate()
    },
  })
}

/**
 * Watches scenario_version in every query response (/scenario is polled every 5 s). When it
 * changes outside this tab's own decisions (API restart, reset, new event), the cached optimizer
 * result and its recommendation alert are dropped and time-based views are refetched.
 */
export function useScenarioVersionGuard() {
  const qc = useQueryClient()
  const invalidate = useInvalidateScenario()
  const seen = useRef<string | null>(null)
  useQuery({ queryKey: qk.scenario, queryFn: () => api<Scenario>('/api/scenario'), retry: false, refetchInterval: 5000 })
  useEffect(() => qc.getQueryCache().subscribe((e) => {
    if (e.type !== 'updated' || e.action.type !== 'success') return
    const v = (e.query.state.data as { scenario_version?: unknown } | undefined)?.scenario_version
    if (typeof v !== 'string') return
    useConsole.getState().syncVersion(v)
    if (seen.current !== null && seen.current !== v) invalidate() // views cached for older versions
    seen.current = v
  }), [qc, invalidate])
}

/** HYPOTHETICAL: computed on a copy of the scenario by the API; nothing live changes. */
export const useWhatIf = () =>
  useMutation({
    mutationFn: ({ minute, events }: { minute: number; events: NewEvent[] }) =>
      api<WhatIfResult>('/api/whatif', { method: 'POST', body: JSON.stringify({ at: fmt(minute), events }) }),
  })

/** Scrubber range on every page: first timetabled time - 10 to last + 10 (display only). */
export function useClockRange() {
  const scenario = useScenario()
  const network = useNetwork(scenario.data?.timetable)
  const setRange = useSim((s) => s.setRange)
  useEffect(() => {
    if (!network.data) return
    const times = network.data.schedule.flatMap((s) => [s.sched_dep, s.sched_arr]).filter(Boolean).map((x) => toMin(x as string))
    if (times.length) setRange([Math.min(...times) - 10, Math.max(...times) + 10])
  }, [network.data, setRange])
}
