// Conflicts and Alerts (page 5; CONTROLLER and ANALYST). Full lists at the sim clock and the alert
// history of the current scenario, all from GET /api/alerts: the backend detects, explains (Phase 7
// templates) and attributes every change to an event or decision. The UI only filters and links.
// Acknowledge (CONTROLLER) is logged to the audit log by the API; acknowledged rows stay, dimmed.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { BellRing, CheckCheck, CircleSlash, History, MapPinned, Route as RouteIcon, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AlertCategory, AlertEpisode, AlertRow, AlertsAt } from '../api/types'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { Tabs } from '../components/ui/Tabs'
import { ClockBar } from '../features/console/ClockBar'
import { DriverList } from '../features/console/DriverList'
import { api, ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { fadeUp, staggerContainer } from '../lib/motion'
import { useCan } from '../lib/permissions'
import { fmt } from '../lib/time'
import { DEMO_START, useSim } from '../store/sim'
import { toast, type Tone } from '../store/toast'

const CATEGORY_LABEL: Record<AlertCategory, string> = {
  CONFLICT: 'Rule-based conflict', UNCERTAIN: 'Uncertain clash (real day)', ML_WATCH: 'ML watchlist', CLOSURE: 'Closure',
}
const SEVERITIES = ['CRITICAL', 'WARNING', 'UNCERTAIN', 'WATCH', 'INFO'] as const

function tone(row: { severity: string; status?: string }): Tone {
  if (row.status === 'RESOLVED') return 'success'
  if (row.status === 'REDUCED') return 'info'
  return ({ CRITICAL: 'critical', WARNING: 'warning', UNCERTAIN: 'info', WATCH: 'ai', INFO: 'info' } as Record<string, Tone>)[row.severity] ?? 'info'
}

function statusWord(r: AlertRow): string {
  if (r.status === 'RESOLVED') return 'Risk resolved by accepted plan'
  if (r.status === 'REDUCED') return `Risk reduced by plan (${r.baseline_wait_min} -> ${r.plan_wait_min} min wait)`
  if (r.status === 'UPCOMING') return 'upcoming'
  return r.severity.toLowerCase()
}

function mapLink(section: string, trains: string[]) {
  const q = new URLSearchParams({ section })
  if (trains.length) q.set('trains', trains.join(','))
  return `/console?${q}`
}
function timelineLink(section: string, trains: string[]) {
  const q = new URLSearchParams({ section })
  if (trains.length) q.set('train', trains[trains.length - 1])
  return `/timeline?${q}`
}

type Filters = { severity: string; category: string; train: string; section: string; search: string }

function matches(r: { severity: string; category: AlertCategory; trains: string[]; section_id: string }, f: Filters) {
  if (f.severity && r.severity !== f.severity) return false
  if (f.category && r.category !== f.category) return false
  if (f.train && !r.trains.includes(f.train)) return false
  if (f.section && r.section_id !== f.section) return false
  const q = f.search.trim().toLowerCase()
  if (q && !r.trains.some((t) => t.toLowerCase().includes(q))) return false
  return true
}

export function Alerts() {
  const minute = useSim((s) => s.minute)
  const at = fmt(minute)
  const qc = useQueryClient()
  const control = useCan('control')
  const [tab, setTab] = useState<'current' | 'history'>('current')
  const [f, setF] = useState<Filters>({ severity: '', category: '', train: '', section: '', search: '' })
  const q = useQuery({
    queryKey: ['alerts', minute],
    queryFn: () => api<AlertsAt>(`/api/alerts?at=${at}`),
    placeholderData: keepPreviousData,
    retry: false,
  })
  const ack = useMutation({
    mutationFn: (key: string) => api<{ key: string }>('/api/alerts/ack', { method: 'POST', body: JSON.stringify({ key, at }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] })
      toast({ tone: 'success', title: 'Alert acknowledged', description: 'Logged in the audit log with your user and the time.' })
    },
    onError: (e) => toast({ tone: 'warning', title: 'Not acknowledged', description: e instanceof ApiError ? e.message : 'Request failed' }),
  })

  const d = q.data
  const options = useMemo(() => {
    const rows = [...(d?.current ?? []), ...(d?.history ?? [])]
    return {
      trains: [...new Set(rows.flatMap((r) => r.trains))].sort(),
      sections: [...new Set(rows.map((r) => r.section_id))].sort(),
    }
  }, [d])
  const current = (d?.current ?? []).filter((r) => matches(r, f))
  const history = (d?.history ?? []).filter((r) => matches(r, f))
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }))
  const sel = 'h-10 rounded-lg border border-line/20 bg-canvas-1 px-3 text-sm text-ink'

  if (q.isError && !d) {
    const err = q.error
    return (
      <Panel initial="hidden" animate="show" className="mx-auto max-w-5xl">
        <EmptyState icon={<CircleSlash className="h-7 w-7" />} title={err instanceof ApiError && err.status === 403 ? 'Not available for your role' : 'The API is not reachable'}>
          {err instanceof Error ? err.message : 'Start the API from the backend folder.'}
        </EmptyState>
      </Panel>
    )
  }

  const ackButton = (key: string, acknowledged: unknown) => acknowledged ? null : (
    <Button size="sm" variant="ghost" icon={<CheckCheck className="h-4 w-4" aria-hidden />} lockedReason={control.reason}
      loading={ack.isPending && ack.variables === key} onClick={() => ack.mutate(key)}>Acknowledge</Button>
  )

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <motion.div variants={fadeUp}>
        <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Conflicts and alerts</p>
        <h1 className="text-3xl font-bold xl:text-4xl">Every alert, and where it came from</h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          Rule-based conflicts, uncertain clashes on real days, the ML watchlist and closures at the clock, plus the history of
          this scenario: when each alert appeared and cleared, and which event or decision caused it. Computed by the API.
        </p>
      </motion.div>

      <motion.div variants={fadeUp}><ClockBar resetTo={DEMO_START} /></motion.div>

      <motion.div variants={fadeUp} className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {(Object.keys(CATEGORY_LABEL) as AlertCategory[]).map((c) => (
          <button key={c} type="button" aria-pressed={f.category === c}
            onClick={() => setF((x) => ({ ...x, category: x.category === c ? '' : c }))}
            className={cn('glass rounded-xl p-4 text-left transition-colors hover:bg-surface-raised/60',
              f.category === c && 'ring-1 ring-signal-cyan/60')}>
            <p className="font-mono text-3xl font-bold tabular">{d ? d.counts[c] : '-'}</p>
            <p className="text-sm text-ink-muted">{CATEGORY_LABEL[c]} at {d?.at ?? at}</p>
          </button>
        ))}
      </motion.div>

      <Panel>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-dim">Severity
            <select value={f.severity} onChange={set('severity')} className={sel}>
              <option value="">All</option>{SEVERITIES.map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-dim">Type
            <select value={f.category} onChange={set('category')} className={sel}>
              <option value="">All</option>{(Object.keys(CATEGORY_LABEL) as AlertCategory[]).map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-dim">Train
            <select value={f.train} onChange={set('train')} className={sel}>
              <option value="">All</option>{options.trains.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-dim">Section
            <select value={f.section} onChange={set('section')} className={sel}>
              <option value="">All</option>{options.sections.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-xs text-ink-dim">Search by train number
            <span className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-dim" aria-hidden />
              <input value={f.search} onChange={set('search')} placeholder="e.g. T202 or 22627" className={cn(sel, 'w-full pl-9')} />
            </span>
          </label>
          {Object.values(f).some(Boolean) && (
            <Button size="sm" variant="ghost" onClick={() => setF({ severity: '', category: '', train: '', section: '', search: '' })}>Clear filters</Button>
          )}
        </div>
        {d?.ml_note && <p className="mt-3 text-sm text-ink-muted">Model note: {d.ml_note}</p>}
        {d && d.posting_clock_missing.length > 0 && (
          <p className="mt-2 text-sm text-signal-amber">
            Posted without a clock (counted as known from the start in the history): {d.posting_clock_missing.join(', ')}
          </p>
        )}
      </Panel>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'current' | 'history')} label="Alert view" items={[
        { value: 'current', label: `At ${d?.at ?? at} (${current.length})` },
        { value: 'history', label: `History (${history.length})` },
      ]}><span /></Tabs>

      {q.isPending ? <Panel><SkeletonRows rows={5} /></Panel> : tab === 'current' ? (
        <Panel>
          <PanelTitle hint={d ? `${d.data_label} · version ${d.scenario_version}` : undefined}>
            <span className="inline-flex items-center gap-2"><BellRing className="h-5 w-5 text-signal-cyan" aria-hidden /> Alerts at {d?.at}</span>
          </PanelTitle>
          {current.length === 0 ? (
            <p className="text-ink-muted">{d?.current.length ? 'No alert matches the filters.' : 'No alert at this time.'}</p>
          ) : (
            <ul className="space-y-3">
              {current.map((r) => (
                <li key={r.key} className={cn('rounded-xl border border-line/15 bg-canvas-0/40 p-4 transition-opacity',
                  r.acknowledged && 'opacity-55')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <SignalBadge tone={tone(r)}>{statusWord(r)}</SignalBadge>
                    <span className="text-xs uppercase tracking-wider text-ink-dim">{CATEGORY_LABEL[r.category]}</span>
                    <h3 className={cn('font-semibold text-ink', r.status === 'RESOLVED' && 'line-through decoration-ink-dim')}>{r.title}</h3>
                    {r.acknowledged && (
                      <span className="text-xs text-ink-muted">Acknowledged by {r.acknowledged.by} ({r.acknowledged.at_utc} UTC)</span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-ink">{r.explanation}</p>
                  {r.drivers.length > 0 && <DriverList drivers={r.drivers} />}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Link to={mapLink(r.section_id, r.trains)} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm text-ink-muted hover:bg-white/5 hover:text-ink">
                      <MapPinned className="h-4 w-4" aria-hidden /> Show on map
                    </Link>
                    <Link to={timelineLink(r.section_id, r.trains)} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm text-ink-muted hover:bg-white/5 hover:text-ink">
                      <RouteIcon className="h-4 w-4" aria-hidden /> Show on timeline
                    </Link>
                    {ackButton(r.key, r.acknowledged)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ) : (
        <Panel>
          <PanelTitle hint="sim time; cause = the event or decision that took effect in that minute">
            <span className="inline-flex items-center gap-2"><History className="h-5 w-5 text-signal-cyan" aria-hidden /> Alert history up to {d?.at}</span>
          </PanelTitle>
          {history.length === 0 ? <p className="text-ink-muted">{d?.history.length ? 'No alert matches the filters.' : 'No alert has been raised in this scenario up to this time.'}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[56rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-ink-dim">
                  <tr className="border-b border-line/15">
                    <th className="py-2 pr-3 font-medium">Alert</th><th className="px-2 font-medium">Appeared</th>
                    <th className="px-2 font-medium">Cleared</th><th className="px-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((e: AlertEpisode) => (
                    <tr key={`${e.key}-${e.appeared}`} className={cn('border-b border-line/10 align-top', e.acknowledged && 'opacity-55')}>
                      <td className="py-2 pr-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <SignalBadge tone={tone(e)}>{e.severity.toLowerCase()}</SignalBadge>
                          <span className="font-medium text-ink">{e.title}</span>
                        </div>
                        <p className="mt-1 text-xs text-ink-dim">{CATEGORY_LABEL[e.category]}{e.acknowledged ? ` · acknowledged by ${e.acknowledged.by}` : ''}</p>
                      </td>
                      <td className="px-2 py-2"><span className="font-mono text-ink">{e.appeared}</span><p className="text-xs text-ink-muted">{e.appeared_cause.text}</p></td>
                      <td className="px-2 py-2">
                        {e.cleared ? <><span className="font-mono text-ink">{e.cleared}</span><p className="text-xs text-ink-muted">{e.cleared_cause?.text}</p></>
                          : <SignalBadge tone="warning">still active</SignalBadge>}
                      </td>
                      <td className="px-2 py-2">
                        <div className="flex flex-wrap justify-end gap-1">
                          <Link to={mapLink(e.section_id, e.trains)} aria-label={`Show ${e.title} on map`} title="Show on map"
                            className="rounded-lg p-2 text-ink-muted hover:bg-white/5 hover:text-ink"><MapPinned className="h-4 w-4" aria-hidden /></Link>
                          <Link to={timelineLink(e.section_id, e.trains)} aria-label={`Show ${e.title} on timeline`} title="Show on timeline"
                            className="rounded-lg p-2 text-ink-muted hover:bg-white/5 hover:text-ink"><RouteIcon className="h-4 w-4" aria-hidden /></Link>
                          {ackButton(e.key, e.acknowledged)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
    </motion.div>
  )
}
