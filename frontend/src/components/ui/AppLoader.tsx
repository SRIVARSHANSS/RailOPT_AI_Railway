import { motion, useReducedMotion } from 'framer-motion'

/** A small train running along a glowing track. Transform-only animation. */
export function AppLoader({ label = 'Loading RailOpt AI' }: { label?: string }) {
  const reduce = useReducedMotion()
  return (
    <div role="status" aria-label={label} className="flex flex-col items-center gap-4">
      <div className="relative h-10 w-64 overflow-hidden">
        {/* track: rails + sleepers + glow */}
        <div aria-hidden className="absolute inset-x-0 top-1/2 h-px -translate-y-[3px] bg-signal-cyan/70 shadow-[0_0_12px_2px_rgb(var(--c-cyan)/0.45)]" />
        <div aria-hidden className="absolute inset-x-0 top-1/2 h-px translate-y-[3px] bg-signal-cyan/70 shadow-[0_0_12px_2px_rgb(var(--c-cyan)/0.45)]" />
        <div aria-hidden className="absolute inset-x-0 top-1/2 h-3 -translate-y-1/2 bg-[repeating-linear-gradient(90deg,rgb(var(--c-line)/0.25)_0_2px,transparent_2px_14px)]" />
        {/* train */}
        <motion.div
          aria-hidden
          className="absolute top-[calc(50%-7px)] flex items-center gap-0.5"
          initial={{ x: reduce ? 104 : -60 }}
          animate={reduce ? { x: 104 } : { x: 260 }}
          transition={reduce ? { duration: 0 } : { duration: 1.6, repeat: Infinity, ease: [0.65, 0, 0.35, 1] }}
        >
          <span className="h-3.5 w-9 rounded-l-[10px] rounded-r-sm bg-gradient-to-r from-signal-cyan to-sky-300 shadow-[0_0_18px_4px_rgb(var(--c-cyan)/0.55)]" />
          <span className="h-3.5 w-7 rounded-sm bg-sky-300/80" />
          <span className="h-3.5 w-7 rounded-sm bg-sky-300/60" />
        </motion.div>
      </div>
      <p className="font-mono text-sm text-ink-muted">{label}...</p>
    </div>
  )
}
