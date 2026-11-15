// Time-distance (Marey) geometry. Pure drawing helpers: every time, km, wait, stop and delay
// comes from GET /api/timeline. Nothing here decides anything about the railway.
import type { TimelineRow } from '../../api/types'

/** A point in data space: minutes, km, and the lane (0 = main line, 1 = alternate lane). */
export type Pt = { t: number; km: number; lane: 0 | 1 }

/** Points of one section trip, from the end of the previous trip (dwell + signal wait are flat). */
export function rowPoints(row: TimelineRow, prev: TimelineRow | undefined): Pt[] {
  const lane = row.alternate ? 1 : 0
  const pts: Pt[] = []
  if (prev) pts.push({ t: prev.exit_min, km: prev.to_km, lane: 0 })
  else if (row.wait_min > 0) pts.push({ t: row.entry_min - row.wait_min, km: row.from_km, lane: 0 })
  pts.push({ t: row.entry_min, km: row.from_km, lane: 0 })
  if (lane) pts.push({ t: row.entry_min, km: row.from_km, lane }) // step into the alternate lane at the station
  // running time excludes the minutes stood still (the API's `stops`), as in the console
  const run = Math.max(1, row.exit_min - row.entry_min - row.stopped_min)
  let stood = 0
  for (const s of row.stops) {
    const km = row.from_km + ((row.to_km - row.from_km) * (s.start_min - row.entry_min - stood)) / run
    pts.push({ t: s.start_min, km, lane }, { t: s.end_min, km, lane })
    stood += s.end_min - s.start_min
  }
  pts.push({ t: row.exit_min, km: row.to_km, lane })
  if (lane) pts.push({ t: row.exit_min, km: row.to_km, lane: 0 }) // and back onto the main line at the far station
  return pts
}

export type TrainRows = { train_id: string; rows: TimelineRow[] }

export function byTrain(rows: TimelineRow[]): TrainRows[] {
  const m = new Map<string, TimelineRow[]>()
  for (const r of rows) m.set(r.train_id, [...(m.get(r.train_id) ?? []), r])
  return [...m.entries()]
    .map(([train_id, rs]) => ({ train_id, rows: rs.sort((a, b) => a.entry_min - b.entry_min) }))
    .sort((a, b) => a.train_id.localeCompare(b.train_id))
}

/** The whole path of a train: section trips joined (shared points removed). */
export function trainPoints(rows: TimelineRow[]): Pt[] {
  const out: Pt[] = []
  rows.forEach((r, i) => {
    const pts = rowPoints(r, rows[i - 1])
    out.push(...(i === 0 ? pts : pts.slice(1)))
  })
  return out
}

/** Time span covered by rows (with padding), in minutes. */
export function timeExtent(rows: TimelineRow[], pad = 8): [number, number] {
  if (!rows.length) return [9 * 60 + 30, 12 * 60]
  let lo = Infinity, hi = -Infinity
  for (const r of rows) {
    lo = Math.min(lo, r.entry_min - r.wait_min)
    hi = Math.max(hi, r.exit_min)
  }
  return [lo - pad, hi + pad]
}

/** Train-type colours (tokens); always shown with the train id as well. */
export const TYPE_COLOR: Record<string, string> = {
  EXPRESS: 'rgb(var(--c-express))',
  PASSENGER: 'rgb(var(--c-passenger))',
  FREIGHT: 'rgb(var(--c-freight))',
  // REAL corridor types (all expresses), told apart by tone; the legend names the type
  SUPERFAST: 'rgb(var(--c-cyan))',
  PREMIUM: 'rgb(var(--c-violet))',
}
