import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import type { Tone } from '../../store/toast'
import { toneClass, toneIcon } from './tones'

/** Status pill: colour + icon + text, so meaning never depends on colour alone. */
export function SignalBadge({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium', toneClass[tone], className)}>
      {toneIcon[tone]}
      {children}
    </span>
  )
}

const trainClass: Record<string, string> = {
  EXPRESS: 'text-train-express border-train-express/40 bg-train-express/10',
  PASSENGER: 'text-train-passenger border-train-passenger/40 bg-train-passenger/10',
  FREIGHT: 'text-train-freight border-train-freight/40 bg-train-freight/10',
}

export function TrainChip({ id, type }: { id: string; type: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 rounded-lg border px-2 py-0.5 text-sm', trainClass[type] ?? toneClass.info)}>
      <span className="font-mono font-semibold tabular">{id}</span>
      <span className="text-[0.7rem] uppercase tracking-wider opacity-90">{type.toLowerCase()}</span>
    </span>
  )
}

/** Permanent label: everything on screen is simulated decision support. */
export function SimulatedBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-signal-amber/50 bg-signal-amber/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-signal-amber"
      title="All data is simulated on a sample corridor. RailOpt AI advises a human controller and controls nothing."
    >
      <span className="h-1.5 w-1.5 rounded-full bg-signal-amber animate-pulse-dot" aria-hidden />
      {compact ? 'Simulated' : 'Simulated data - decision support only'}
    </span>
  )
}
