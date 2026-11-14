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
import { Console } from './pages/Console'
import { Disruptions } from './pages/Disruptions'
import { Strategies } from './pages/Strategies'
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
                  <Route path="/console" element={<Console />} />
                  <Route path="/disruptions" element={<Disruptions />} />
                  <Route path="/strategies" element={<Strategies />} />
                  <Route path="/timeline" element={<Placeholder title="Timeline" what="Planned vs actual time-distance chart." />} />
                  <Route path="/design" element={<DesignSystem />} />
                </Route>
                <Route path="*" element={<Navigate to="/console" replace />} />
              </Routes>
            </Suspense>
            <Toaster />
          </BrowserRouter>
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  )
}
