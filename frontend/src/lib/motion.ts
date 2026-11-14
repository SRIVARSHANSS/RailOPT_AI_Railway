// One source of truth for motion. Animate transform / opacity only.
import type { Transition, Variants } from 'framer-motion'

export const duration = {
  instant: 0.08,
  fast: 0.14,
  base: 0.22,
  slow: 0.36,
  route: 0.5, // page wipe; must stay under 0.6 s
} as const

export const ease = {
  out: [0.16, 1, 0.3, 1] as const, // expo-out: arrivals
  inOut: [0.65, 0, 0.35, 1] as const, // wipes
  in: [0.7, 0, 0.84, 0] as const, // exits
}

export const spring = {
  snappy: { type: 'spring', stiffness: 520, damping: 34, mass: 0.7 } satisfies Transition,
  soft: { type: 'spring', stiffness: 260, damping: 30 } satisfies Transition,
}

export const stagger = { children: 0.05, rows: 0.035 }

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: duration.slow, ease: ease.out } },
}

export const staggerContainer = (gap: number = stagger.children): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: gap } },
})

export const page: Variants = {
  initial: { opacity: 0, x: 24 },
  enter: { opacity: 1, x: 0, transition: { duration: duration.slow, ease: ease.out, delay: 0.12 } },
  exit: { opacity: 0, x: -24, transition: { duration: duration.fast, ease: ease.in } },
}

export const hover = { lift: { y: -2 }, press: { scale: 0.97 } }
