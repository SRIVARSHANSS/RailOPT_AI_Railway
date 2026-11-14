import { useEffect } from 'react'
import { minuteMs, useSim } from '../../store/sim'

/** Advances the simulation clock while playing (one rAF loop for the whole app). */
export function ClockDriver() {
  const playing = useSim((s) => s.playing)
  useEffect(() => {
    if (!playing) return
    let raf = 0
    const loop = () => {
      const { speed, minuteStartedAt, advance } = useSim.getState()
      if (performance.now() - minuteStartedAt >= minuteMs(speed)) advance()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [playing])
  return null
}
