import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { RouteStreak } from './components/layout/RouteStreak'
import { AppLoader } from './components/ui/AppLoader'
import { BackgroundGrid } from './components/ui/BackgroundGrid'
import { Toaster } from './components/ui/Toaster'
import { TooltipProvider } from './components/ui/Tooltip'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { Placeholder } from './pages/Placeholder'
import { useSession } from './store/session'

const DesignSystem = lazy(() => import('./pages/DesignSystem').then((m) => ({ default: m.DesignSystem })))

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } } })

function RequireRole({ children }: { children: ReactNode }) {
  const role = useSession((s) => s.role)
  return role ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* reducedMotion="user": every Framer animation honours prefers-reduced-motion */}
      <MotionConfig reducedMotion="user">
        <TooltipProvider>
          <BrowserRouter>
            <BackgroundGrid />
            <RouteStreak />
            <Suspense fallback={<div className="grid min-h-screen place-items-center"><AppLoader /></div>}>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route element={<RequireRole><AppShell /></RequireRole>}>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/conflicts" element={<Placeholder title="Conflicts" what="Detector conflicts with ML probability, top drivers and the watchlist." />} />
                  <Route path="/optimize" element={<Placeholder title="Optimize" what="Strategy comparison, recommendation and accept / reject." />} />
                  <Route path="/timeline" element={<Placeholder title="Timeline" what="Planned vs actual time-distance chart." />} />
                  <Route path="/scenario" element={<Placeholder title="Scenario" what="Reset the scenario and post events." />} />
                  <Route path="/design" element={<DesignSystem />} />
                </Route>
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </Suspense>
            <Toaster />
          </BrowserRouter>
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  )
}
