import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Check, Loader2 } from 'lucide-react'
import { useState, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { duration, ease, spring } from '../../lib/motion'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onAnimationStart' | 'onDragStart' | 'onDragEnd' | 'onDrag'> & {
  variant?: Variant
  size?: Size
  loading?: boolean
  success?: boolean
  icon?: ReactNode
  /** Role gate: when set, the button is disabled and this says why (tooltip + screen readers). */
  lockedReason?: string
}

const variants: Record<Variant, string> = {
  // AI / primary action: cyan gradient, dark text (11:1 contrast)
  primary:
    'bg-gradient-to-r from-signal-cyan to-sky-400 text-canvas-0 font-semibold shadow-[0_8px_24px_-8px_rgb(var(--c-cyan)/0.6)] hover:shadow-glow',
  secondary: 'glass text-ink hover:bg-surface-raised/60',
  ghost: 'text-ink-muted hover:text-ink hover:bg-white/5',
  danger: 'bg-signal-red/15 text-signal-red border border-signal-red/40 hover:bg-signal-red/25',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm gap-1.5',
  md: 'h-11 px-4 text-[0.95rem] gap-2',
  lg: 'h-12 px-6 text-base gap-2.5',
}

type Ripple = { id: number; x: number; y: number; size: number }

export function Button({ lockedReason, ...props }: Props) {
  if (!lockedReason) return <ButtonInner {...props} />
  // a disabled button gets no hover events: the wrapper carries the tooltip
  return (
    <span className="inline-flex" title={lockedReason}>
      <ButtonInner {...props} disabled aria-description={lockedReason} />
    </span>
  )
}

function ButtonInner({ variant = 'secondary', size = 'md', loading, success, icon, className, children, onClick, disabled, ...rest }: Omit<Props, 'lockedReason'>) {
  const reduce = useReducedMotion()
  const [ripples, setRipples] = useState<Ripple[]>([])
  const busy = loading || success

  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    if (!reduce) {
      const rect = e.currentTarget.getBoundingClientRect()
      const s = Math.max(rect.width, rect.height) * 2
      setRipples((r) => [...r, { id: Date.now(), x: e.clientX - rect.left - s / 2, y: e.clientY - rect.top - s / 2, size: s }])
    }
    onClick?.(e)
  }

  return (
    <motion.button
      whileHover={disabled || busy || reduce ? undefined : { y: -2 }}
      whileTap={disabled || busy || reduce ? undefined : { scale: 0.97 }}
      transition={spring.snappy}
      className={cn(
        'relative inline-flex select-none items-center justify-center overflow-hidden rounded-xl transition-[box-shadow,background-color,color] duration-200 disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || busy}
      aria-busy={loading || undefined}
      onClick={handleClick}
      {...rest}
    >
      {ripples.map((r) => (
        <motion.span
          key={r.id}
          aria-hidden
          className="pointer-events-none absolute rounded-full bg-white/25"
          style={{ left: r.x, top: r.y, width: r.size, height: r.size }}
          initial={{ scale: 0, opacity: 0.5 }}
          animate={{ scale: 1, opacity: 0 }}
          transition={{ duration: 0.6, ease: ease.out }}
          onAnimationComplete={() => setRipples((all) => all.filter((x) => x.id !== r.id))}
        />
      ))}
      <AnimatePresence mode="wait" initial={false}>
        {loading ? (
          <motion.span key="loading" className="inline-flex items-center gap-2" {...swap}>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            <span>{children}</span>
          </motion.span>
        ) : success ? (
          <motion.span key="success" className="inline-flex items-center gap-2" {...swap}>
            <motion.span initial={{ scale: 0.4, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} transition={spring.snappy}>
              <Check className="h-4 w-4" aria-hidden />
            </motion.span>
            <span>{children}</span>
          </motion.span>
        ) : (
          <motion.span key="idle" className="inline-flex items-center gap-2" {...swap}>
            {icon}
            {children}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  )
}

const swap = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: duration.fast, ease: ease.out },
}
