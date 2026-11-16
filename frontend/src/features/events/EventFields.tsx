import { AnimatePresence, motion } from 'framer-motion'
import { useState, type FormEvent, type ReactNode } from 'react'
import type { NewEvent } from '../../api/hooks'
import type { EventType, Network } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { SkeletonRows } from '../../components/ui/Skeleton'
import { TabPanel, Tabs } from '../../components/ui/Tabs'
import { cn } from '../../lib/cn'
import { duration, ease } from '../../lib/motion'
import { inputCls } from './inputCls'

const TAB_ITEMS = [
  { value: 'STOPPAGE', label: 'Stoppage' },
  { value: 'DELAY', label: 'Delay' },
  { value: 'TRACK_UNAVAILABLE', label: 'Track closure' },
  { value: 'PLATFORM_UNAVAILABLE', label: 'Platform', disabled: true, hint: 'not modelled yet' },
]

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm text-ink-muted">
      {label}
      {children}
    </label>
  )
}

/** Event form shared by Disruptions (posts to the scenario) and What-If (adds to a hypothesis).
 *  `onSubmit` resolves to an error message to show inline (e.g. the API's 422), or null. */
export function EventFields({ network, onSubmit, submitLabel, doneLabel, disabled, idPrefix, lockedReason }: {
  network: Network | undefined
  onSubmit: (ev: NewEvent) => Promise<string | null>
  submitLabel: string
  doneLabel: string
  disabled?: boolean
  lockedReason?: string
  idPrefix: string
}) {
  const [type, setType] = useState<EventType>('STOPPAGE')
  const [train, setTrain] = useState('T202')
  const [location, setLocation] = useState('')
  const [start, setStart] = useState('10:10')
  const [dur, setDur] = useState(5)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [ok, setOk] = useState(false)

  if (!network) return <SkeletonRows rows={3} label="Loading network" />

  const needsTrain = type === 'STOPPAGE' || type === 'DELAY'
  const locations = type === 'DELAY'
    ? network.stations.map((s) => ({ v: s.code, l: `${s.code} - ${s.name}` }))
    : network.sections.map((s) => ({ v: s.section_id, l: `${s.section_id} (${s.from_station}-${s.to_station})` }))
  const loc = locations.some((o) => o.v === location) ? location : locations[0]?.v ?? ''

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const err = await onSubmit({ event_type: type, train_id: needsTrain ? train : null, location: loc, start_time: start, duration_min: dur })
    setBusy(false)
    if (err) return setError(err)
    setOk(true)
    window.setTimeout(() => setOk(false), 1400)
  }

  return (
    <Tabs value={type} onValueChange={(v) => { setType(v as EventType); setError(null) }} label={`${idPrefix} event type`} items={TAB_ITEMS}>
      {TAB_ITEMS.filter((t) => !t.disabled).map((t) => (
        <TabPanel key={t.value} value={t.value}>
          <motion.form key={t.value} onSubmit={submit} className="grid gap-4 sm:grid-cols-2"
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: duration.base, ease: ease.out }}>
            {needsTrain && (
              <Field label="Train">
                <select value={train} onChange={(e) => setTrain(e.target.value)} className={inputCls}>
                  {network.trains.map((tr) => <option key={tr.train_id} value={tr.train_id}>{tr.train_id} - {tr.train_type.toLowerCase()}</option>)}
                </select>
              </Field>
            )}
            <Field label={type === 'DELAY' ? 'Station' : 'Section'}>
              <select value={loc} onChange={(e) => setLocation(e.target.value)} className={inputCls}>
                {locations.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
              </select>
            </Field>
            <Field label="Start time (sim)">
              <input type="text" inputMode="numeric" pattern="([01]\d|2[0-3]):[0-5]\d" value={start} onChange={(e) => setStart(e.target.value)}
                className={cn(inputCls, 'font-mono')} aria-describedby={`${idPrefix}-start-help`} required />
              <span id={`${idPrefix}-start-help`} className="text-xs text-ink-dim">HH:MM</span>
            </Field>
            <Field label="Duration (min)">
              <input type="number" min={1} max={600} value={dur} onChange={(e) => setDur(Number(e.target.value))} className={cn(inputCls, 'font-mono')} required />
            </Field>
            <div className="sm:col-span-2">
              <AnimatePresence>
                {error && (
                  <motion.p role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                    className="mb-3 rounded-xl border border-signal-red/40 bg-signal-red/10 px-3 py-2 text-sm text-signal-red">{error}</motion.p>
                )}
              </AnimatePresence>
              <Button type="submit" variant="primary" loading={busy} success={ok} disabled={disabled} lockedReason={lockedReason}>{ok ? doneLabel : submitLabel}</Button>
            </div>
          </motion.form>
        </TabPanel>
      ))}
    </Tabs>
  )
}
