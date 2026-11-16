// Network and Train Management (ADMIN, Phase 8). View every corridor; edit only the 'custom'
// SIMULATED copy (seeded from full_day). reference / full_day stay as the committed CSVs and the
// REAL DG -> MDU corridor is read-only with its sources. All validation is done by the API
// (row-level errors); the UI only shows what it returns.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { AlertTriangle, Download, FileUp, Lock, Plus, RotateCcw, Save, Trash2, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { DataBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { Panel } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { Tabs } from '../components/ui/Tabs'
import { api, ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { staggerContainer } from '../lib/motion'
import { toast } from '../store/toast'

type Kind = 'stations' | 'sections' | 'trains' | 'schedule'
type Row = Record<string, string>
type Corridor = {
  name: string; data_label: string; editable: boolean; summary: string
  columns: Record<Kind, string[]>; tables: Record<Kind, Row[]>
  licence?: string | null; manifest?: unknown; source_columns?: string[]
}
type RowError = { table: Kind; row: number; line: number; column: string | null; value: string | null; message: string }

const CORRIDORS = [
  { value: 'custom', label: 'Custom (editable)' },
  { value: 'reference', label: 'Reference' },
  { value: 'full_day', label: 'Full day' },
  { value: 'dg_mdu', label: 'Real DG-MDU' },
]
const KINDS: { value: Kind; label: string }[] = [
  { value: 'stations', label: 'Stations' }, { value: 'sections', label: 'Sections' },
  { value: 'trains', label: 'Trains' }, { value: 'schedule', label: 'Schedule' },
]

function rowErrors(e: unknown): RowError[] {
  if (e instanceof ApiError) {
    const d = (e.body as { detail?: { errors?: RowError[] } } | null)?.detail
    if (d && typeof d === 'object' && Array.isArray(d.errors)) return d.errors
  }
  return []
}

function toCsv(columns: string[], rows: Row[]): string {
  const q = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
  return [columns.join(','), ...rows.map((r) => columns.map((c) => q(r[c] ?? '')).join(','))].join('\n') + '\n'
}

export function NetworkAdmin() {
  const [name, setName] = useState('custom')
  const [kind, setKind] = useState<Kind>('stations')
  const qc = useQueryClient()
  const corridor = useQuery({ queryKey: ['admin-network', name], queryFn: () => api<Corridor>(`/api/admin/network/${name}`) })
  const data = corridor.data
  const columns = data ? (name === 'dg_mdu' ? Object.keys(data.tables[kind][0] ?? {}) : data.columns[kind]) : []
  const [draft, setDraft] = useState<Row[] | null>(null)
  const [errors, setErrors] = useState<RowError[]>([])
  useEffect(() => { setDraft(null); setErrors([]) }, [name, kind, data])
  const rows = draft ?? data?.tables[kind] ?? []
  const dirty = draft !== null

  const done = (c: Corridor, what: string) => {
    qc.setQueryData(['admin-network', 'custom'], c)
    qc.invalidateQueries({ queryKey: ['network'] })
    setDraft(null)
    setErrors([])
    toast({ tone: 'success', title: what, description: 'Validated by the API and saved. Load it with Disruptions -> Reset -> Custom.' })
  }
  const failed = (e: unknown, what: string) => {
    const errs = rowErrors(e)
    setErrors(errs)
    toast({ tone: 'warning', title: `${what}: nothing saved`, description: e instanceof ApiError ? e.message : 'Request failed' })
  }
  const save = useMutation({
    mutationFn: () => api<Corridor>(`/api/admin/network/custom/${kind}`, { method: 'PUT', body: JSON.stringify({ rows }) }),
    onSuccess: (c) => done(c, `${kind} saved`), onError: (e) => failed(e, 'Save'),
  })
  const importCsv = useMutation({
    mutationFn: (csv: string) => api<Corridor>(`/api/admin/network/custom/${kind}/import`, { method: 'POST', body: JSON.stringify({ csv }) }),
    onSuccess: (c) => done(c, `${kind} imported from CSV`), onError: (e) => failed(e, 'Import'),
  })
  const reseed = useMutation({
    mutationFn: () => api<Corridor>('/api/admin/network/custom/reset', { method: 'POST' }),
    onSuccess: (c) => done(c, 'Custom corridor reset to full_day'), onError: (e) => failed(e, 'Reset'),
  })
  const file = useRef<HTMLInputElement>(null)
  const pickFile = async (f: File | undefined) => {
    if (!f) return
    importCsv.mutate(await f.text())
    if (file.current) file.current.value = ''
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([toCsv(columns, rows)], { type: 'text/csv' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: `${name}_${kind}.csv` })
    a.click()
    URL.revokeObjectURL(url)
  }
  const edit = (i: number, c: string, v: string) => setDraft(rows.map((r, k) => (k === i ? { ...r, [c]: v } : r)))
  const bad = (i: number, c: string) => errors.some((e) => e.table === kind && e.row === i + 1 && e.column === c)
  const busy = save.isPending || importCsv.isPending || reseed.isPending

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div>
        <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Administration</p>
        <h1 className="text-3xl font-bold xl:text-4xl">Network and train management</h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          Edit the <b className="text-ink">custom</b> SIMULATED corridor (stations, sections, trains, schedule) or import a CSV per table.
          The API checks every row against the others and saves all rows or none. Reference and full day stay as the committed files
          (the tests, the demo and the evaluation depend on them); the real corridor is read-only.
        </p>
      </div>

      <Tabs value={name} onValueChange={setName} items={CORRIDORS} label="Corridor"><span /></Tabs>

      <Panel>
        <div className="flex flex-wrap items-center gap-3">
          <DataBadge label={data?.data_label} />
          {data && !data.editable && <span className="inline-flex items-center gap-1.5 text-sm text-ink-muted"><Lock className="h-4 w-4" aria-hidden />Read-only</span>}
        </div>
        {data && <p className="mt-3 text-ink">{data.summary}</p>}
        {data?.source_columns && (
          <p className="mt-2 text-sm text-ink-muted">Source columns in these tables: {data.source_columns.join(', ')} (values such as DERIVED, ASSUMED, CALIBRATED, DATASET_ROUTE, ESTIMATED).</p>
        )}
        {data?.licence && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-signal-cyan">Data licence and attribution</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-canvas-0/60 p-3 text-xs text-ink-muted">{data.licence}</pre>
          </details>
        )}
      </Panel>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Tabs value={kind} onValueChange={(v) => setKind(v as Kind)} items={KINDS} label="Table"><span /></Tabs>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" icon={<Download className="h-4 w-4" aria-hidden />} onClick={download} disabled={!rows.length}>Download CSV</Button>
            {data?.editable && <>
              <input ref={file} type="file" accept=".csv,text/csv" className="sr-only" aria-label={`Import ${kind} CSV`}
                onChange={(e) => pickFile(e.target.files?.[0])} />
              <Button size="sm" icon={<FileUp className="h-4 w-4" aria-hidden />} onClick={() => file.current?.click()} loading={importCsv.isPending}>Import CSV</Button>
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-4 w-4" aria-hidden />} onClick={() => reseed.mutate()} disabled={busy}>Reset to full day</Button>
            </>}
          </div>
        </div>

        {errors.length > 0 && (
          <div role="alert" className="mt-4 rounded-xl border border-signal-red/40 bg-signal-red/10 p-3 text-sm">
            <p className="flex items-center gap-2 font-semibold text-ink"><AlertTriangle className="h-4 w-4 text-signal-red" aria-hidden />{errors.length} problem(s); nothing was saved</p>
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-ink">
              {errors.map((e, k) => (
                <li key={k}><span className="font-mono text-ink-muted">{e.table}{e.row ? ` row ${e.row} (CSV line ${e.line})` : ' (header / whole table)'}{e.column ? `, ${e.column}` : ''}:</span> {e.message}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-4">
          {corridor.isPending ? <SkeletonRows rows={6} /> : corridor.error ? <p className="text-signal-red">{(corridor.error as Error).message}</p> : (
            <div className="max-h-[32rem] overflow-auto rounded-xl border border-line/10">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-canvas-1/95 text-xs uppercase tracking-wider text-ink-dim">
                  <tr><th className="px-2 py-2">#</th>{columns.map((c) => <th key={c} className="whitespace-nowrap px-2 py-2">{c}</th>)}{data?.editable && <th className="px-2 py-2"><span className="sr-only">Delete</span></th>}</tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-line/10">
                      <td className="px-2 py-1 font-mono text-xs text-ink-dim">{i + 1}</td>
                      {columns.map((c) => (
                        <td key={c} className="px-1 py-1">
                          {data?.editable ? (
                            <input aria-label={`${kind} row ${i + 1} ${c}`} value={r[c] ?? ''} onChange={(e) => edit(i, c, e.target.value)}
                              aria-invalid={bad(i, c) || undefined}
                              className={cn('h-8 w-full min-w-[5.5rem] rounded-md border bg-canvas-0/50 px-2 font-mono text-xs text-ink',
                                bad(i, c) ? 'border-signal-red' : 'border-line/15')} />
                          ) : <span className="whitespace-nowrap px-1 font-mono text-xs text-ink">{r[c]}</span>}
                        </td>
                      ))}
                      {data?.editable && (
                        <td className="px-1"><button type="button" aria-label={`Delete ${kind} row ${i + 1}`} onClick={() => setDraft(rows.filter((_, k) => k !== i))}
                          className="rounded-md p-1.5 text-ink-dim hover:bg-white/5 hover:text-signal-red"><Trash2 className="h-4 w-4" aria-hidden /></button></td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data?.editable && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" icon={<Plus className="h-4 w-4" aria-hidden />}
              onClick={() => setDraft([...rows, Object.fromEntries(columns.map((c) => [c, '']))])}>Add row</Button>
            <span className="ml-auto" />
            {dirty && <Button size="sm" variant="ghost" icon={<Undo2 className="h-4 w-4" aria-hidden />} onClick={() => { setDraft(null); setErrors([]) }}>Discard changes</Button>}
            <Button size="sm" variant="primary" icon={<Save className="h-4 w-4" aria-hidden />} disabled={!dirty || busy} loading={save.isPending} onClick={() => save.mutate()}>
              Save {kind}
            </Button>
          </div>
        )}
      </Panel>
    </motion.div>
  )
}
