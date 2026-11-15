import { AnimatePresence, motion } from 'framer-motion'
import { BrainCircuit, CircleCheck, ShieldAlert, Sparkles, TrendingDown, TriangleAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { ConflictsAt, PlanStatus } from '../../api/types'
import { buildAlerts } from './alerts'
import { EmptyState } from '../../components/ui/EmptyState'
import { cn } from '../../lib/cn'
import { duration, ease } from '../../lib/motion'
import { useConsole } from '../../store/sim'

const style = {
  CRITICAL: { box: 'border-signal-red/50 bg-signal-red/10', text: 'text-signal-red', icon: ShieldAlert },
  WARNING: { box: 'border-signal-amber/45 bg-signal-amber/10', text: 'text-signal-amber', icon: TriangleAlert },
  RECOMMENDATION: { box: 'border-signal-cyan/50 bg-signal-cyan/10', text: 'text-signal-cyan', icon: Sparkles },
  RESOLVED: { box: 'border-signal-green/40 bg-signal-green/10', text: 'text-signal-green', icon: CircleCheck },
  // calm cyan: the plan lowered the risk but did not remove it
  REDUCED: { box: 'border-signal-cyan/30 bg-signal-cyan/[0.06]', text: 'text-signal-cyan', icon: TrendingDown },
} as const

export function AlertsFeed({ conflicts, loading, plan }: { conflicts: ConflictsAt | undefined; loading: boolean; plan?: PlanStatus }) {
  const { highlight, setHighlight, optimize, decided } = useConsole()
  const navigate = useNavigate()
  const alerts = buildAlerts(conflicts, optimize, decided, plan)

  if (!loading && alerts.length === 0) {
    return <EmptyState icon={<CircleCheck className="h-7 w-7" />} title="No alerts">No conflict is known at this time.</EmptyState>
  }
  return (
    <ul className="space-y-2.5" aria-label="Live alerts">
      <AnimatePresence initial={false}>
        {alerts.map((a) => {
          const s = style[a.level]
          const Icon = a.key.startsWith('ml-') && a.level === 'WARNING' ? BrainCircuit : s.icon
          const selected = highlight?.key === a.key
          return (
            <motion.li key={a.key} layout initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }}
              transition={{ duration: duration.base, ease: ease.out }}>
              <button
                aria-pressed={selected}
                onClick={() => {
                  if (a.level === 'RECOMMENDATION') return navigate('/strategies')
                  setHighlight(selected ? null : { key: a.key, section_id: a.section_id, trains: a.trains })
                }}
                className={cn('flex w-full gap-3 rounded-xl border p-3 text-left transition-shadow', s.box,
                  selected && 'shadow-[0_0_0_2px_rgb(var(--c-cyan))]')}
              >
                <span className={cn('mt-0.5 shrink-0', s.text, a.level === 'CRITICAL' && 'animate-heartbeat')}>
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <span className="min-w-0">
                  <span className={cn('block font-semibold', s.text)}>{a.title}</span>
                  {a.struck && <span className="mt-0.5 block text-sm text-signal-green line-through decoration-2"><span className="sr-only">Resolved: </span>{a.struck}</span>}
                  <span className="mt-0.5 block text-sm text-ink">{a.detail}</span>
                </span>
              </button>
            </motion.li>
          )
        })}
      </AnimatePresence>
    </ul>
  )
}
