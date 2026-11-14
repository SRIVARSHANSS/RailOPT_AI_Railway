import { ShieldAlert, Sparkles, TriangleAlert, CircleCheck, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Tone } from '../../store/toast'

export const toneClass: Record<Tone, string> = {
  success: 'text-signal-green border-signal-green/40 bg-signal-green/10',
  warning: 'text-signal-amber border-signal-amber/40 bg-signal-amber/10',
  critical: 'text-signal-red border-signal-red/40 bg-signal-red/10',
  ai: 'text-signal-cyan border-signal-cyan/40 bg-signal-cyan/10',
  info: 'text-ink-muted border-line/25 bg-white/5',
}

export const toneIcon: Record<Tone, ReactNode> = {
  success: <CircleCheck className="h-3.5 w-3.5" aria-hidden />,
  warning: <TriangleAlert className="h-3.5 w-3.5" aria-hidden />,
  critical: <ShieldAlert className="h-3.5 w-3.5" aria-hidden />,
  ai: <Sparkles className="h-3.5 w-3.5" aria-hidden />,
  info: <Info className="h-3.5 w-3.5" aria-hidden />,
}
