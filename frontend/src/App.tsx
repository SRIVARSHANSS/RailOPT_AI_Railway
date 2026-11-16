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
import { WhatIf } from './pages/WhatIf'
import { Login } from './pages/Login'
import { useBootstrapSession } from './api/auth'
import { can, type Action } from './lib/permissions'
import { useSession } from './store/session'

const Analytics = lazy(() => import('./pages/Analytics').then((m) => ({ default: m.Analytics })))
const ModelInsights = lazy(() => import('./pages/ModelInsights').then((m) => ({ default: m.ModelInsights })))
const Timeline = lazy(() => import('./pages/Timeline').then((m) => ({ default: m.Timeline })))
const DesignSystem = lazy(() => import('./pages/DesignSystem').then((m) => ({ default: m.DesignSystem })))
const Users = lazy(() => import('./pages/Users').then((m) => ({ default: m.Users })))
const NetworkAdmin = lazy(() => import('./pages/NetworkAdmin').then((m) => ({ default: m.NetworkAdmin })))

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } } })

/** Signed-in users only: asks the API (cookie session) once on start. */
function RequireAuth({ children }: { children: ReactNode }) {
  useBootstrapSession()
  const status = useSession((s) => s.status)
  if (status === 'unknown') return <div className="grid min-h-screen place-items-center"><AppLoader /></div>
  return status === 'signed-in' ? children : <Navigate to="/login" replace />
}

/** Pages for one role (the API refuses the calls anyway; this keeps the UI honest). */
function RequireRole({ action, children }: { action: Action; children: ReactNode }) {
  const role = useSession((s) => s.user?.role)
  return can(role, action) ? children : <Navigate to="/console" replace />
}

function LoginRoute() {
  useBootstrapSession()
  return <Login />
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
                <Route path="/login" element={<LoginRoute />} />
                <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                  <Route path="/console" element={<Console />} />
                  <Route path="/disruptions" element={<Disruptions />} />
                  <Route path="/strategies" element={<Strategies />} />
                  <Route path="/whatif" element={<WhatIf />} />
                  <Route path="/timeline" element={<Timeline />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/model" element={<ModelInsights />} />
                  <Route path="/design" element={<DesignSystem />} />
                  <Route path="/admin/users" element={<RequireRole action="admin"><Users /></RequireRole>} />
                  <Route path="/admin/network" element={<RequireRole action="admin"><NetworkAdmin /></RequireRole>} />
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
