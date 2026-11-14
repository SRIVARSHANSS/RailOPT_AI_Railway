import * as Toast from '@radix-ui/react-toast'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { ease, duration } from '../../lib/motion'
import { useToasts, type Tone } from '../../store/toast'
import { toneIcon } from './tones'

const edge: Record<Tone, string> = {
  success: 'bg-signal-green',
  warning: 'bg-signal-amber',
  critical: 'bg-signal-red',
  ai: 'bg-signal-cyan',
  info: 'bg-ink-dim',
}
const iconColour: Record<Tone, string> = {
  success: 'text-signal-green',
  warning: 'text-signal-amber',
  critical: 'text-signal-red',
  ai: 'text-signal-cyan',
  info: 'text-ink-muted',
}

/** Radix toasts (accessible live region) that slide in with a signal-colour edge. */
export function Toaster() {
  const { toasts, dismiss } = useToasts()
  return (
    <Toast.Provider swipeDirection="right" duration={5000}>
      <AnimatePresence>
        {toasts.map((t) => (
          <Toast.Root key={t.id} asChild forceMount type={t.tone === 'critical' ? 'foreground' : 'background'}
            onOpenChange={(open) => !open && dismiss(t.id)}>
            <motion.li
              layout
              initial={{ opacity: 0, x: 48 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 48 }}
              transition={{ duration: duration.base, ease: ease.out }}
              className="glass relative flex w-[22rem] gap-3 overflow-hidden py-3 pl-5 pr-10"
            >
              <span aria-hidden className={cn('absolute inset-y-0 left-0 w-1', edge[t.tone])} />
              <span className={cn('mt-0.5', iconColour[t.tone])}>{toneIcon[t.tone]}</span>
              <div className="min-w-0">
                <Toast.Title className="font-semibold">{t.title}</Toast.Title>
                {t.description ? <Toast.Description className="mt-0.5 text-sm text-ink-muted">{t.description}</Toast.Description> : null}
              </div>
              <Toast.Close aria-label="Dismiss notification" className="absolute right-2 top-2 rounded-lg p-1.5 text-ink-dim hover:text-ink">
                <X className="h-4 w-4" aria-hidden />
              </Toast.Close>
            </motion.li>
          </Toast.Root>
        ))}
      </AnimatePresence>
      <Toast.Viewport className="fixed bottom-5 right-5 z-[60] flex flex-col gap-3 outline-none" />
    </Toast.Provider>
  )
}
