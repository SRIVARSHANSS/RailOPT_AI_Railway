import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { CircleSlash, MapPin, Split, TrainFront, Waypoints } from 'lucide-react'
import { EmptyState } from '../components/ui/EmptyState'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { Skeleton } from '../components/ui/Skeleton'
import { StatTile } from '../components/ui/StatTile'
import { TrainChip } from '../components/ui/Badges'
import { api, type NetworkSummary } from '../lib/api'
import { staggerContainer } from '../lib/motion'
import { ROLE_LABEL, useSession } from '../store/session'

/** Part 1: the corridor configuration from the API (real counts, simulated corridor). */
export function Dashboard() {
  const role = useSession((s) => s.role)
  const ref = useQuery({ queryKey: ['network', 'reference'], queryFn: () => api<NetworkSummary>('/api/network?timetable=reference') })
  const full = useQuery({ queryKey: ['network', 'full_day'], queryFn: () => api<NetworkSummary>('/api/network?timetable=full_day') })

  return (
    <div className="mx-auto max-w-6xl">
      <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Signed in as {role ? ROLE_LABEL[role] : '-'}</p>
      <h1 className="mt-1 text-3xl font-bold xl:text-4xl">Corridor A - B - C - D</h1>
      <p className="mt-2 max-w-2xl text-ink-muted">
        Sample corridor configuration, loaded live from the API. The live map, conflicts and recommendations arrive in Phase 9 part 2.
      </p>

      {ref.isError || full.isError ? (
        <Panel initial="hidden" animate="show" className="mt-8">
          <EmptyState icon={<CircleSlash className="h-7 w-7" />} title="The API is not reachable">
            Start it from the backend folder with <code className="font-mono text-ink">uvicorn app.main:app --reload</code>, then reload this page.
          </EmptyState>
        </Panel>
      ) : !ref.data || !full.data ? (
        <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4" role="status" aria-label="Loading corridor">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
        </div>
      ) : (
        <motion.div variants={staggerContainer()} initial="hidden" animate="show">
          <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile label="Stations" value={ref.data.stations.length} icon={<MapPin className="h-4 w-4" />} />
            <StatTile label="Sections" value={ref.data.sections.length} icon={<Split className="h-4 w-4" />}
              foot={`${ref.data.sections.filter((s) => s.tracks === 1).length} single-track`} />
            <StatTile label="Reference trains" value={ref.data.trains.length} icon={<TrainFront className="h-4 w-4" />} foot="T101 scenario" />
            <StatTile label="Full-day trains" value={full.data.trains.length} icon={<Waypoints className="h-4 w-4" />} foot="06:00 - 14:00" accent="text-signal-cyan" />
          </div>
          <Panel className="mt-6">
            <PanelTitle hint="reference timetable">Trains</PanelTitle>
            <div className="flex flex-wrap gap-2">
              {ref.data.trains.map((t) => <TrainChip key={t.train_id} id={t.train_id} type={t.train_type} />)}
            </div>
          </Panel>
        </motion.div>
      )}
    </div>
  )
}
