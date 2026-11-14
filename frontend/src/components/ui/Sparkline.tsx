/** Tiny trend line of recently polled values (display only). */
export function Sparkline({ values, className = 'stroke-signal-cyan' }: { values: number[]; className?: string }) {
  if (values.length < 2) return <svg viewBox="0 0 80 24" className="h-6 w-20" aria-hidden />
  const max = Math.max(1, ...values)
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 80},${22 - (v / max) * 20}`).join(' ')
  return (
    <svg viewBox="0 0 80 24" className="h-6 w-20" aria-hidden>
      <polyline points={pts} fill="none" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" className={className} />
    </svg>
  )
}
