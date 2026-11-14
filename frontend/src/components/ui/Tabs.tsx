import * as RTabs from '@radix-ui/react-tabs'
import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { spring } from '../../lib/motion'

export type TabItem = { value: string; label: string; disabled?: boolean; hint?: string }

/** Radix tabs with a sliding active indicator (shared layoutId). Disabled items stay visible. */
export function Tabs({ value, onValueChange, items, label, children }: {
  value: string
  onValueChange: (v: string) => void
  items: TabItem[]
  label: string
  children: ReactNode
}) {
  return (
    <RTabs.Root value={value} onValueChange={onValueChange}>
      <RTabs.List aria-label={label} className="inline-flex flex-wrap rounded-xl border border-line/15 bg-canvas-0/40 p-1">
        {items.map((it) => (
          <RTabs.Trigger key={it.value} value={it.value} disabled={it.disabled} title={it.hint}
            className={cn('relative rounded-lg px-4 py-2 text-sm transition-colors disabled:cursor-not-allowed',
              value === it.value ? 'text-ink' : it.disabled ? 'text-ink-dim' : 'text-ink-muted hover:text-ink')}>
            {value === it.value ? (
              <motion.span layoutId={`tab-${label}`} transition={spring.snappy} className="absolute inset-0 rounded-lg bg-surface-raised/80 shadow-panel" />
            ) : null}
            <span className="relative">{it.label}</span>
            {it.disabled && it.hint ? <span className="relative ml-2 text-xs italic">{it.hint}</span> : null}
          </RTabs.Trigger>
        ))}
      </RTabs.List>
      {children}
    </RTabs.Root>
  )
}

export const TabPanel = ({ value, children }: { value: string; children: ReactNode }) => (
  <RTabs.Content value={value} className="mt-4 outline-none">{children}</RTabs.Content>
)
