import { cn } from '../../lib/cn'

/** Shimmer placeholder (transform-only animation, static for reduced motion). */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('relative overflow-hidden rounded-lg bg-white/[0.06]', className)}>
      <div className="animate-shimmer absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
    </div>
  )
}

export function SkeletonRows({ rows = 4, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-9 w-9 rounded-xl" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-2/5" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  )
}
