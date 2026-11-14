import { motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { duration, ease } from '../../lib/motion'

/** Animated empty state: a gently floating icon with a soft halo. */
export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.slow, ease: ease.out }}
      className="flex flex-col items-center px-6 py-14 text-center"
    >
      <div className="relative mb-5">
        <div aria-hidden className="absolute inset-0 -m-4 rounded-full bg-signal-cyan/10 blur-xl" />
        <motion.div
          aria-hidden
          className="relative grid h-16 w-16 place-items-center rounded-2xl border border-line/20 bg-surface-raised/60 text-signal-cyan"
          animate={reduce ? undefined : { y: [0, -6, 0] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
        >
          {icon}
        </motion.div>
      </div>
      <h3 className="text-xl font-semibold">{title}</h3>
      {children ? <p className="mt-2 max-w-md text-ink-muted">{children}</p> : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </motion.div>
  )
}
