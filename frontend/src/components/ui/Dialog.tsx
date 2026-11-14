import * as RD from '@radix-ui/react-dialog'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { duration, ease } from '../../lib/motion'

/** Accessible modal (focus trap, Esc, aria) with a scale + fade entrance. */
export function Dialog({ open, onOpenChange, title, description, children }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open ? (
          <RD.Portal forceMount>
            <RD.Overlay asChild forceMount>
              <motion.div className="fixed inset-0 z-50 bg-canvas-0/70 backdrop-blur-sm"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: duration.base }} />
            </RD.Overlay>
            <RD.Content asChild forceMount>
              <motion.div
                className="glass fixed inset-0 z-50 m-auto h-fit w-[min(32rem,92vw)] p-6"
                initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: duration.base, ease: ease.out }}
              >
                <RD.Title className="font-display text-xl font-semibold">{title}</RD.Title>
                {description ? <RD.Description className="mt-1 text-ink-muted">{description}</RD.Description> : null}
                <div className="mt-5">{children}</div>
                <RD.Close aria-label="Close" className="absolute right-3 top-3 rounded-lg p-2 text-ink-dim hover:text-ink">
                  <X className="h-4 w-4" aria-hidden />
                </RD.Close>
              </motion.div>
            </RD.Content>
          </RD.Portal>
        ) : null}
      </AnimatePresence>
    </RD.Root>
  )
}
