import { motion, type HTMLMotionProps } from 'framer-motion'
import { cn } from '../../lib/cn'
import { fadeUp } from '../../lib/motion'

/** Glass panel. Inside a staggerContainer it enters with fadeUp. */
export function Panel({ className, children, ...rest }: HTMLMotionProps<'section'>) {
  return (
    <motion.section variants={fadeUp} className={cn('glass glass-focus p-5', className)} {...rest}>
      {children}
    </motion.section>
  )
}

export function PanelTitle({ children, hint }: { children: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-3">
      <h2 className="text-lg font-semibold text-ink">{children}</h2>
      {hint ? <span className="text-sm text-ink-dim">{hint}</span> : null}
    </div>
  )
}
