// Display helpers for stored results. Labels are words; every number comes from the API.
import { useLayoutEffect, useState, type RefObject } from 'react'
import type { Ci } from '../../api/types'

export const METHOD_LABEL: Record<string, string> = {
  NO_REPLANNING: 'No re-planning (FCFS)',
  PRIORITY_DISPATCH: 'Priority dispatch',
  SINGLE_SHOT: 'RailOpt single-shot',
  DYNAMIC: 'RailOpt dynamic',
  DYNAMIC_ML: 'Dynamic + ML, 1-min buffers',
  DYNAMIC_ML_B2: 'A: 2-min buffers',
  DYNAMIC_ML_B3: 'A: 3-min buffers',
  DYNAMIC_ML_PROP: 'B: round(3p)-min buffers',
  DYNAMIC_ML_TRIGGER: 'C: ML-triggered re-planning',
}
export const BASELINES = new Set(['NO_REPLANNING', 'PRIORITY_DISPATCH'])
export const label = (m: string) => METHOD_LABEL[m] ?? m

export const METRIC_LABEL: Record<string, { label: string; digits: number; unit?: string }> = {
  weighted_delay: { label: 'Weighted delay', digits: 1 },
  avg_delay_min: { label: 'Avg delay', digits: 2, unit: 'min/train' },
  total_delay_min: { label: 'Total delay', digits: 1, unit: 'min' },
  max_delay_min: { label: 'Max delay', digits: 1, unit: 'min' },
  throughput_trains_per_hour: { label: 'Throughput', digits: 2, unit: 'trains/h' },
  trains_waited: { label: 'Trains that waited', digits: 2 },
  total_wait_min: { label: 'Wait', digits: 1, unit: 'min' },
}

export const f = (x: number, d = 1) => (Number.isFinite(x) ? x.toFixed(d) : '-')
export const ci = (c: Ci, d = 1) => `[${f(c[0], d)}, ${f(c[1], d)}]`
export const signed = (x: number, d = 1) => `${x > 0 ? '+' : ''}${f(x, d)}`
export const pct = (x: number, d = 1) => `${f(x * 100, d)}%`

/** Container width for responsive SVG charts. */
export function useWidth(ref: RefObject<HTMLElement | null>, min = 320) {
  const [w, setW] = useState(800)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(min, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref, min])
  return w
}
