import { motion } from 'framer-motion'
import { Activity, Clock3, ShieldAlert, TrainFront } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Kpis } from '../../api/types'
import { CountUp } from '../../components/ui/CountUp'
import { Sparkline } from '../../components/ui/Sparkline'
import { cn } from '../../lib/cn'
import { fadeUp, staggerContainer } from '../../lib/motion'

/** KPIs straight from /api/state; sparklines are the last polled values. */
export function KpiStrip({ kpis, history }: { kpis: Kpis; history: Kpis[] }) {
  const series = (k: keyof Kpis) => history.map((h) => h[k])
  return (
    <motion.div variants={staggerContainer()} initial="hidden" animate="show" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Tile label="Active trains" icon={<TrainFront className="h-4 w-4" />} value={kpis.active_trains} spark={series('active_trains')} />
      <Tile label="Delayed trains" icon={<Clock3 className="h-4 w-4" />} value={kpis.delayed_trains} spark={series('delayed_trains')}
        tone={kpis.delayed_trains > 0 ? 'text-signal-amber' : undefined} sparkClass="stroke-signal-amber" />
      <Tile label="Conflicts (known)" icon={<ShieldAlert className="h-4 w-4" />} value={kpis.conflicts} spark={series('conflicts')}
        tone={kpis.conflicts > 0 ? 'text-signal-red' : 'text-signal-green'} sparkClass="stroke-signal-red" />
      <Tile label="Avg delay (active)" icon={<Activity className="h-4 w-4" />} value={kpis.avg_delay_min} decimals={1} unit="min" spark={series('avg_delay_min')} />
    </motion.div>
  )
}

function Tile({ label, icon, value, spark, tone, unit, decimals = 0, sparkClass }: {
  label: string; icon: ReactNode; value: number; spark: number[]; tone?: string; unit?: string; decimals?: number; sparkClass?: string
}) {
  return (
    <motion.div variants={fadeUp} className="glass px-4 py-3">
      <div className="flex items-center justify-between text-sm text-ink-muted">
        <span>{label}</span>
        <span className="text-ink-dim">{icon}</span>
      </div>
      <div className="mt-1 flex items-end justify-between gap-2">
        <div className={cn('text-3xl font-semibold', tone ?? 'text-ink')}>
          <CountUp value={value} decimals={decimals} durationS={0.5} />
          {unit ? <span className="ml-1 text-base font-normal text-ink-muted">{unit}</span> : null}
        </div>
        <Sparkline values={spark} className={sparkClass} />
      </div>
    </motion.div>
  )
}
