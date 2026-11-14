import { motion } from 'framer-motion'
import { Inbox, Sparkles, Zap } from 'lucide-react'
import { useState } from 'react'
import { AppLoader } from '../components/ui/AppLoader'
import { SignalBadge, SimulatedBadge, TrainChip } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { TabPanel, Tabs } from '../components/ui/Tabs'
import { staggerContainer } from '../lib/motion'
import { toast } from '../store/toast'

const SWATCHES = [
  ['On time', 'bg-signal-green'], ['Warning', 'bg-signal-amber'], ['Critical', 'bg-signal-red'],
  ['AI / recommendation', 'bg-signal-cyan'], ['Accent', 'bg-signal-violet'],
  ['Express', 'bg-train-express'], ['Passenger', 'bg-train-passenger'], ['Freight', 'bg-train-freight'],
] as const

/** Living style guide for the "Midnight Signal" system. No data here is a metric. */
export function DesignSystem() {
  const [state, setState] = useState<'idle' | 'loading' | 'success'>('idle')
  const [tab, setTab] = useState('loading')
  const [dialog, setDialog] = useState(false)

  const run = () => {
    setState('loading')
    window.setTimeout(() => setState('success'), 1200)
    window.setTimeout(() => setState('idle'), 2600)
  }

  return (
    <motion.div className="mx-auto max-w-6xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div>
        <h1 className="text-3xl font-bold xl:text-4xl">Design system</h1>
        <p className="mt-2 text-ink-muted">"Midnight Signal": colour carries meaning, motion stays under 600 ms, everything works with reduced motion.</p>
      </div>

      <Panel>
        <PanelTitle hint="signals mean something; train colours always come with a label">Colour</PanelTitle>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {SWATCHES.map(([label, cls]) => (
            <div key={label} className="flex items-center gap-3 rounded-xl border border-line/10 bg-canvas-0/40 p-3">
              <span className={`h-8 w-8 rounded-lg ${cls}`} aria-hidden />
              <span className="text-sm">{label}</span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <PanelTitle hint="hover lift, press, ripple, loading, success">Buttons</PanelTitle>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} loading={state === 'loading'} success={state === 'success'} onClick={run}>
              {state === 'success' ? 'Plan ready' : state === 'loading' ? 'Optimizing' : 'Run optimizer (demo)'}
            </Button>
            <Button>Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Reject</Button>
          </div>
        </Panel>

        <Panel>
          <PanelTitle hint="slide in with a signal edge">Toasts</PanelTitle>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => toast({ tone: 'critical', title: 'Critical conflict', description: 'Example text for the component gallery.' })}>Critical</Button>
            <Button size="sm" onClick={() => toast({ tone: 'warning', title: 'Warning', description: 'Example text for the component gallery.' })}>Warning</Button>
            <Button size="sm" onClick={() => toast({ tone: 'ai', title: 'Recommendation ready', description: 'Example text for the component gallery.' })}>AI</Button>
            <Button size="sm" onClick={() => toast({ tone: 'success', title: 'Plan accepted', description: 'Example text for the component gallery.' })}>Success</Button>
          </div>
        </Panel>

        <Panel>
          <PanelTitle>Badges and train chips</PanelTitle>
          <div className="flex flex-wrap gap-2">
            <SignalBadge tone="success">On time</SignalBadge>
            <SignalBadge tone="warning">Warning</SignalBadge>
            <SignalBadge tone="critical">Critical</SignalBadge>
            <SignalBadge tone="ai">AI recommendation</SignalBadge>
            <SimulatedBadge />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <TrainChip id="T101" type="EXPRESS" />
            <TrainChip id="T202" type="PASSENGER" />
            <TrainChip id="T303" type="FREIGHT" />
          </div>
        </Panel>

        <Panel>
          <PanelTitle hint="Radix: keyboard and screen-reader ready">Tabs and dialog</PanelTitle>
          <Tabs value={tab} onValueChange={setTab} label="States" items={[{ value: 'loading', label: 'Loading' }, { value: 'empty', label: 'Empty' }, { value: 'loader', label: 'App loader' }]}>
            <TabPanel value="loading"><SkeletonRows rows={3} /></TabPanel>
            <TabPanel value="empty">
              <EmptyState icon={<Inbox className="h-7 w-7" />} title="No conflicts">Nothing to resolve right now.</EmptyState>
            </TabPanel>
            <TabPanel value="loader"><div className="py-8"><AppLoader /></div></TabPanel>
          </Tabs>
          <div className="mt-4">
            <Button icon={<Zap className="h-4 w-4" />} onClick={() => setDialog(true)}>Open dialog</Button>
          </div>
        </Panel>
      </div>

      <Dialog open={dialog} onOpenChange={setDialog} title="Accept recommendation?" description="Example dialog for the component gallery.">
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={() => setDialog(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => setDialog(false)}>Accept</Button>
        </div>
      </Dialog>
    </motion.div>
  )
}
