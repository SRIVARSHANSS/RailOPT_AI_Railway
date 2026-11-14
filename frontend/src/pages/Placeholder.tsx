import { Construction } from 'lucide-react'
import { Panel } from '../components/ui/Panel'
import { EmptyState } from '../components/ui/EmptyState'

/** Honest placeholder for views that arrive in Phase 9 part 2. */
export function Placeholder({ title, what }: { title: string; what: string }) {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="mb-6 text-3xl font-bold">{title}</h1>
      <Panel initial="hidden" animate="show">
        <EmptyState icon={<Construction className="h-7 w-7" />} title="Coming in Phase 9 part 2">
          {what} The API for it already exists and is tested.
        </EmptyState>
      </Panel>
    </div>
  )
}
