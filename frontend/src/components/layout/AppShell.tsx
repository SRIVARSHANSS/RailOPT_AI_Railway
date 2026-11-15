import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  BarChart3, BrainCircuit, ChevronsLeft, ChevronsRight, Clock, FlaskConical, LogOut, MonitorPlay, Palette, Route, Scale, TrainFront, Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate, useOutlet } from 'react-router-dom'
import { useClockRange, useScenarioVersionGuard } from '../../api/hooks'
import { api, type Health } from '../../lib/api'
import { cn } from '../../lib/cn'
import { duration, page, spring } from '../../lib/motion'
import { fmt } from '../../lib/time'
import { ROLE_LABEL, useSession } from '../../store/session'
import { useSim } from '../../store/sim'
import { DataBadge } from '../ui/Badges'
import { Tooltip } from '../ui/Tooltip'
import { ClockDriver } from './ClockDriver'

const NAV = [
  { to: '/console', label: 'Traffic console', icon: MonitorPlay },
  { to: '/disruptions', label: 'Disruptions', icon: Zap },
  { to: '/strategies', label: 'Strategies', icon: Scale },
  { to: '/whatif', label: 'What-if studio', icon: FlaskConical },
  { to: '/timeline', label: 'Timeline', icon: Route },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/model', label: 'Model insights', icon: BrainCircuit },
  { to: '/design', label: 'Design system', icon: Palette },
]

/** Keeps the outlet of the page that is leaving, so exit animations show the old page. */
function FrozenOutlet() {
  const outlet = useOutlet()
  const [frozen] = useState(outlet)
  return frozen
}

/** Below 1024 px the sidebar is always the icon rail, so the content keeps its width. */
function useWide() {
  const query = '(min-width: 1024px)'
  const [wide, setWide] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setWide(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return wide
}

export function AppShell() {
  const { pathname } = useLocation()
  const wide = useWide()
  const collapsed = useSession((s) => s.sidebarCollapsed) || !wide
  useScenarioVersionGuard()
  useClockRange()
  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[90] focus:rounded-lg focus:bg-canvas-2 focus:px-4 focus:py-2">
        Skip to content
      </a>
      <ClockDriver />
      <Sidebar collapsed={collapsed} canExpand={wide} />
      {/* overflow-x clip: the page slide-in (x: 24px) must never widen the page on phones */}
      <div className="flex min-w-0 flex-1 flex-col overflow-x-clip">
        <TopBar />
        <AnimatePresence mode="wait">
          <motion.main key={pathname} id="main" variants={page} initial="initial" animate="enter" exit="exit"
            className="min-w-0 flex-1 px-4 pb-10 pt-6 sm:px-6 xl:px-10">
            <FrozenOutlet />
          </motion.main>
        </AnimatePresence>
      </div>
    </div>
  )
}

function Sidebar({ collapsed, canExpand }: { collapsed: boolean; canExpand: boolean }) {
  const toggle = useSession((s) => s.toggleSidebar)
  const { pathname } = useLocation()
  return (
    <aside className={cn('sticky top-0 flex h-screen shrink-0 flex-col border-r border-line/10 bg-canvas-0/60 backdrop-blur-xl',
      collapsed ? 'w-[4.75rem]' : 'w-64')}>
      <div className="flex h-16 items-center gap-3 px-5">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-signal-cyan to-signal-violet text-canvas-0 shadow-glow">
          <TrainFront className="h-5 w-5" aria-hidden />
        </div>
        {!collapsed && (
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: duration.base }}
            className="font-display text-lg font-bold tracking-tight">RailOpt <span className="text-signal-cyan">AI</span></motion.span>
        )}
      </div>

      <nav aria-label="Main" className="mt-4 flex-1 space-y-1 px-3">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = pathname.startsWith(to)
          const link = (
            <NavLink key={to} to={to} aria-label={collapsed ? label : undefined}
              className={cn('relative flex h-11 items-center gap-3 rounded-xl px-3 text-[0.95rem] transition-colors',
                active ? 'text-ink' : 'text-ink-muted hover:bg-white/5 hover:text-ink')}>
              {active && (
                <motion.span layoutId="nav-active" transition={spring.snappy} aria-hidden
                  className="absolute inset-0 rounded-xl border border-signal-cyan/30 bg-signal-cyan/10">
                  <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-signal-cyan shadow-[0_0_10px_rgb(var(--c-cyan))]" />
                </motion.span>
              )}
              <Icon className={cn('relative h-5 w-5 shrink-0', active && 'text-signal-cyan')} aria-hidden />
              {!collapsed && <span className="relative truncate">{label}</span>}
            </NavLink>
          )
          return collapsed ? <Tooltip key={to} content={label} side="right">{link}</Tooltip> : link
        })}
      </nav>

      <div className={cn('p-3', !canExpand && 'hidden')}>
        <button onClick={toggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}
          className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm text-ink-muted hover:bg-white/5 hover:text-ink">
          {collapsed ? <ChevronsRight className="h-5 w-5" aria-hidden /> : <ChevronsLeft className="h-5 w-5" aria-hidden />}
          {!collapsed && 'Collapse'}
        </button>
      </div>
    </aside>
  )
}

function TopBar() {
  const { role, signOut } = useSession()
  const simClock = fmt(useSim((s) => s.minute))
  const playing = useSim((s) => s.playing)
  const navigate = useNavigate()
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    refetchInterval: 15000,
    retry: false,
  })
  const online = health.isSuccess
  return (
    <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-line/10 bg-canvas-1/70 px-4 backdrop-blur-xl sm:gap-4 sm:px-6 xl:px-10">
      <Tooltip content="Scenario clock (simulated time, not wall-clock time)">
        <div className="flex items-center gap-2 rounded-xl border border-line/15 bg-canvas-0/50 px-2 py-1.5 sm:px-3" tabIndex={0}>
          <Clock className="hidden h-4 w-4 text-signal-cyan sm:block" aria-hidden />
          <span className="hidden text-xs uppercase tracking-wider text-ink-dim sm:inline">Sim</span>
          <span className="font-mono text-lg font-semibold tabular text-ink" aria-label={`Simulation clock ${simClock}, ${playing ? 'running' : 'paused'}`}>{simClock}</span>
          {playing && <span className="h-1.5 w-1.5 rounded-full bg-signal-green animate-pulse-dot" aria-hidden />}
        </div>
      </Tooltip>

      <Tooltip content={online ? `API online - timetable ${health.data?.timetable}` : 'API offline - start it with: uvicorn app.main:app --reload'}>
        <span tabIndex={0} className="inline-flex items-center gap-2 text-sm text-ink-muted">
          <span aria-hidden className={cn('h-2 w-2 rounded-full', online ? 'bg-signal-green animate-pulse-dot' : health.isPending ? 'bg-ink-dim' : 'bg-signal-red')} />
          <span className="hidden md:inline">{online ? 'API online' : health.isPending ? 'Connecting' : 'API offline'}</span>
          <span className="sr-only md:hidden">{online ? 'API online' : 'API offline'}</span>
        </span>
      </Tooltip>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <span className="hidden lg:inline-flex"><DataBadge label={health.data?.data_label} /></span>
        <span className="lg:hidden"><DataBadge label={health.data?.data_label} compact /></span>
        {role && (
          <span className="hidden rounded-full border border-signal-violet/40 bg-signal-violet/10 px-3 py-1 sm:inline text-xs font-semibold uppercase tracking-wider text-signal-violet">
            {ROLE_LABEL[role]}
          </span>
        )}
        <Tooltip content="Sign out (demo)">
          <button aria-label="Sign out" onClick={() => { signOut(); navigate('/login') }}
            className="rounded-xl p-2 text-ink-muted hover:bg-white/5 hover:text-ink">
            <LogOut className="h-5 w-5" aria-hidden />
          </button>
        </Tooltip>
      </div>
    </header>
  )
}
