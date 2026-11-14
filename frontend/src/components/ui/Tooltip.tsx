import * as RT from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'

export const TooltipProvider = RT.Provider

export function Tooltip({ content, children, side = 'bottom' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <RT.Root delayDuration={250}>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content
          side={side}
          sideOffset={8}
          className="z-[70] max-w-xs rounded-lg border border-line/20 bg-canvas-2/95 px-3 py-2 text-sm text-ink shadow-panel"
        >
          {content}
          <RT.Arrow className="fill-canvas-2" />
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  )
}
