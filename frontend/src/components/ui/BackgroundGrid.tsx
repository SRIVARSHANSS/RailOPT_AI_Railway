/** Fixed background: a faint grid and diagonal track lines drifting very slowly.
 *  One oversized layer is translated (GPU transform only); static for reduced motion. */
export function BackgroundGrid() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="animate-drift absolute -inset-[160px] opacity-[0.55] will-change-transform"
        style={{
          backgroundImage: [
            // grid
            'linear-gradient(rgb(var(--c-line) / 0.05) 1px, transparent 1px)',
            'linear-gradient(90deg, rgb(var(--c-line) / 0.05) 1px, transparent 1px)',
            // diagonal "track" pairs
            'repeating-linear-gradient(135deg, transparent 0 78px, rgb(var(--c-cyan) / 0.06) 78px 79px, transparent 79px 84px, rgb(var(--c-cyan) / 0.06) 84px 85px, transparent 85px 160px)',
          ].join(','),
          backgroundSize: '40px 40px, 40px 40px, 160px 160px',
        }}
      />
      {/* vignette keeps focus in the centre */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgb(var(--c-canvas-0)/0.75)_100%)]" />
    </div>
  )
}
