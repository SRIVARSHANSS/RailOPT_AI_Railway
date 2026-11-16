import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import type { Driver } from '../../api/types'
import { cn } from '../../lib/cn'

/** The model's top 2-3 SHAP drivers in plain words (API templates). They explain the MODEL'S
 *  score, not a physical cause: "Model risk raised by" / "Model risk lowered by". */
export function DriverList({ drivers, max = 3 }: { drivers: Driver[]; max?: number }) {
  const shown = drivers.slice(0, max)
  return (
    <span className="mt-2 block" role="list" aria-label="Model risk drivers">
      {shown.map((d) => {
        const up = d.direction === 'raises'
        const Icon = up ? ArrowUpRight : ArrowDownRight
        return (
          <span key={d.feature} role="listitem" className="mt-1 flex items-start gap-1.5 text-xs text-ink-muted" title={d.sentence}>
            <Icon className={cn('mt-px h-3.5 w-3.5 shrink-0', up ? 'text-signal-amber' : 'text-signal-green')} aria-hidden />
            <span>
              <span className={cn('font-semibold', up ? 'text-signal-amber' : 'text-signal-green')}>
                {up ? 'Model risk raised by' : 'Model risk lowered by'}:
              </span>{' '}
              {d.text}
            </span>
          </span>
        )
      })}
    </span>
  )
}
