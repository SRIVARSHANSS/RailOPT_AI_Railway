import { motion, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { duration, ease } from '../../lib/motion'

/** "Train passing" light streak that sweeps across on every route change (< 600 ms). */
export function RouteStreak() {
  const { pathname } = useLocation()
  const reduce = useReducedMotion()
  const first = useRef(true)
  const [run, setRun] = useState(0)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    setRun((n) => n + 1)
  }, [pathname])

  if (reduce || run === 0) return null
  return (
    <motion.div
      key={run}
      aria-hidden
      className="pointer-events-none fixed inset-y-0 left-0 z-[80] w-[45vw]"
      initial={{ x: '-50vw', opacity: 0 }}
      animate={{ x: '150vw', opacity: [0, 1, 1, 0] }}
      transition={{ duration: duration.route, ease: ease.inOut, times: [0, 0.15, 0.8, 1] }}
    >
      <div className="absolute inset-y-0 right-0 w-full bg-gradient-to-r from-transparent via-signal-cyan/[0.07] to-signal-cyan/25" />
      <div className="absolute inset-y-0 right-0 w-[3px] bg-signal-cyan shadow-[0_0_30px_8px_rgb(var(--c-cyan)/0.6)]" />
    </motion.div>
  )
}
