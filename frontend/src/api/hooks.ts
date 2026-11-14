// React Query hooks. The UI only displays what the API returns; no railway logic here.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { fmt } from '../lib/time'
import type {
  ConflictsAt, DecisionResult, EventType, Network, OptimizeResult, Scenario, StateAt, Timetable,
} from './types'

export const qk = {
  scenario: ['scenario'] as const,
  network: (t: Timetable) => ['network', t] as const,
  state: (m: number) => ['state', m] as const,
  conflicts: (m: number) => ['conflicts', m] as const,
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

/** Anything that changes the scenario invalidates every time-based view. */
function useInvalidateScenario() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: qk.scenario })
    qc.invalidateQueries({ queryKey: ['state'] })
    qc.invalidateQueries({ queryKey: ['conflicts'] })
  }
}

export function useResetScenario() {
  const invalidate = useInvalidateScenario()
  return useMutation({
    mutationFn: (timetable: Timetable) =>
      api<Scenario>('/api/scenario/reset', { method: 'POST', body: JSON.stringify({ timetable }) }),
    onSuccess: invalidate,
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
    onSuccess: invalidate,
  })
}
