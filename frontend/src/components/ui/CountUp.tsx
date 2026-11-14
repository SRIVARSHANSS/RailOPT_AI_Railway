import { animate, useInView, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/** Counts up to `value` once visible. Reduced motion: shows the final value. */
export function CountUp({ value, decimals = 0, durationS = 0.9 }: { value: number; decimals?: number; durationS?: number }) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const [shown, setShown] = useState(reduce ? value : 0)

  useEffect(() => {
    if (reduce || !inView) {
      if (reduce) setShown(value)
      return
    }
    const controls = animate(0, value, { duration: durationS, ease: [0.16, 1, 0.3, 1], onUpdate: setShown })
    return () => controls.stop()
  }, [value, inView, reduce, durationS])

  return (
    <span ref={ref} className="font-mono tabular">
      {shown.toFixed(decimals)}
    </span>
  )
}
