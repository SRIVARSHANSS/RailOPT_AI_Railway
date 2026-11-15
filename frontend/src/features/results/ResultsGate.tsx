import { AnimatePresence, motion } from 'framer-motion'
import { CircleSlash, FileWarning, RefreshCcw } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { ResultStatus } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/EmptyState'
import { Panel } from '../../components/ui/Panel'
import { SkeletonRows } from '../../components/ui/Skeleton'
import { cn } from '../../lib/cn'
import { duration, ease, staggerContainer } from '../../lib/motion'

/** Loading / offline / missing / outdated states for stored results. Outdated results stay
 *  hidden behind an explicit "show anyway" so stale numbers are never mistaken for current ones. */
export function ResultsGate({ loading, error, status, reasons, command, what, children }: {
  loading: boolean
  error: boolean
  status: ResultStatus | undefined
  reasons: string[]
  command: string
  what: string
  children: ReactNode
}) {
  const [showStale, setShowStale] = useState(false)
  if (error) {
    return (
      <Panel initial="hidden" animate="show">
        <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
          Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app</code>.
        </EmptyState>
      </Panel>
    )
  }
  if (loading || !status) return <Panel><SkeletonRows rows={6} label={`Loading ${what}`} /></Panel>
  if (status === 'missing') {
    return (
      <Panel initial="hidden" animate="show">
        <EmptyState icon={<FileWarning className="h-7 w-7" />} title={`No ${what} yet`}>
          {reasons.join('; ')}. From the backend folder run <code className="font-mono text-ink">{command}</code>.
        </EmptyState>
      </Panel>
    )
  }
  return (
    <>
      {status === 'outdated' && (
        <motion.div role="alert" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: duration.slow, ease: ease.out }}
          className="glass flex flex-wrap items-start gap-4 border border-signal-amber/40 p-5">
          <RefreshCcw className="mt-0.5 h-6 w-6 text-signal-amber" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold text-signal-amber">Outdated - rerun</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-ink">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <p className="mt-2 text-sm text-ink-muted">From the backend folder run <code className="font-mono text-ink">{command}</code>.</p>
          </div>
          <Button variant="secondary" onClick={() => setShowStale((v) => !v)}>
            {showStale ? 'Hide the stored results' : 'Show the stored results anyway'}
          </Button>
        </motion.div>
      )}
      <AnimatePresence>
        {(status === 'ok' || showStale) && (
          // own stagger: these panels mount after the page entrance has finished
          <motion.div key="content" variants={staggerContainer()} initial="hidden" animate="show" exit={{ opacity: 0 }}
            className={cn('space-y-6', status !== 'ok' && 'opacity-60')}>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
