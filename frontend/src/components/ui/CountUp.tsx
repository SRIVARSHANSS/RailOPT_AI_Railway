import { animate, useInView, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/** Counts up to `value` once visible, then animates from the previous value on each change.
 *  Reduced motion: shows the final value. */
export function CountUp({ value, decimals = 0, durationS = 0.9 }: { value: number; decimals?: number; durationS?: number }) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const [shown, setShown] = useState(reduce ? value : 0)
  const last = useRef(reduce ? value : 0)

  useEffect(() => {
    if (reduce) {
      last.current = value
      setShown(value)
      return
    }
    if (!inView) return
    const controls = animate(last.current, value, {
      duration: durationS,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        last.current = v
        setShown(v)
      },
    })
    return () => controls.stop()
  }, [value, inView, reduce, durationS])

  return (
    <span ref={ref} className="font-mono tabular">
      {shown.toFixed(decimals)}
    </span>
  )
}
