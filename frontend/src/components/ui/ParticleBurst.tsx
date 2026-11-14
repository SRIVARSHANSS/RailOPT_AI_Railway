import { motion, useReducedMotion } from 'framer-motion'

/** Subtle celebratory burst (transform + opacity only). Renders nothing for reduced motion. */
export function ParticleBurst({ run, colour = 'bg-signal-cyan' }: { run: number; colour?: string }) {
  const reduce = useReducedMotion()
  if (!run || reduce) return null
  const n = 14
  return (
    <span key={run} aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
      {Array.from({ length: n }, (_, i) => {
        const a = (i / n) * Math.PI * 2
        const r = 54 + (i % 3) * 14
        return (
          <motion.span key={i} className={`absolute h-1.5 w-1.5 rounded-full ${colour}`}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{ x: Math.cos(a) * r, y: Math.sin(a) * r, opacity: 0, scale: 0.4 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }} />
        )
      })}
    </span>
  )
}
