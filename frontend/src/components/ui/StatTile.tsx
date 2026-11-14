import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { fadeUp } from '../../lib/motion'
import { CountUp } from './CountUp'

export function StatTile({ label, value, unit, icon, accent = 'text-ink', foot }: {
  label: string
  value: number
  unit?: string
  icon?: ReactNode
  accent?: string
  foot?: ReactNode
}) {
  return (
    <motion.div variants={fadeUp} className="glass p-4">
      <div className="flex items-center justify-between text-sm text-ink-muted">
        <span>{label}</span>
        <span className="text-ink-dim">{icon}</span>
      </div>
      <div className={cn('mt-2 text-3xl font-semibold', accent)}>
        <CountUp value={value} />
        {unit ? <span className="ml-1 text-base font-normal text-ink-muted">{unit}</span> : null}
      </div>
      {foot ? <div className="mt-1 text-xs text-ink-dim">{foot}</div> : null}
    </motion.div>
  )
}
