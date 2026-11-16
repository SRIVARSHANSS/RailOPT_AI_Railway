import { motion, useReducedMotion } from 'framer-motion'
import { AlertTriangle, ArrowRight, Check, KeyRound, Mail, TrainFront } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useLogin } from '../api/auth'
import { LoginHero } from '../components/layout/LoginHero'
import { SimulatedBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { fadeUp, staggerContainer } from '../lib/motion'
import { useSession } from '../store/session'

const field = 'h-12 w-full rounded-xl border border-white/15 bg-canvas-0/50 pl-11 pr-3 text-ink placeholder:text-ink-dim ' +
  'focus:border-signal-cyan/60 focus:outline-none focus:ring-2 focus:ring-signal-cyan/30'

export function Login() {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const login = useLogin()
  const { status, expired } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [welcome, setWelcome] = useState(false)

  if (status === 'signed-in' && !welcome) return <Navigate to="/console" replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!email || !password || login.isPending) return
    login.mutate({ email, password }, {
      onSuccess: () => {
        setPassword('')
        setWelcome(true)
        window.setTimeout(() => navigate('/console'), reduce ? 0 : 500)
      },
    })
  }
  const err = login.error
  const errText = err instanceof ApiError ? err.message : err ? 'The API is not reachable. Start it from the backend folder.' : null
  const limited = err instanceof ApiError && err.status === 429

  return (
    <div className="relative min-h-screen">
      <LoginHero />
      <main className="mx-auto flex min-h-screen max-w-7xl items-center px-6 py-10 lg:px-12">
        <motion.div variants={staggerContainer(0.08)} initial="hidden" animate="show"
          className="login-glass glass-focus grid w-full max-w-4xl overflow-hidden lg:grid-cols-[1.05fr_1fr]">
          {/* brand side */}
          <div className="relative border-b border-white/10 p-8 lg:border-b-0 lg:border-r lg:border-white/10 lg:p-10">
            <motion.div variants={fadeUp} className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-signal-cyan to-signal-violet text-canvas-0 shadow-glow">
                <TrainFront className="h-6 w-6" aria-hidden />
              </div>
              <SimulatedBadge compact />
            </motion.div>
            <motion.h1 variants={fadeUp} className="mt-8 text-5xl font-bold leading-[1.05] xl:text-6xl">
              RailOpt <span className="bg-gradient-to-r from-signal-cyan to-signal-violet bg-clip-text text-transparent">AI</span>
            </motion.h1>
            <motion.p variants={fadeUp} className="mt-4 text-lg text-ink">
              Predict conflicts, compare re-planning strategies and explain every recommendation, so the controller can decide faster.
            </motion.p>
            <motion.ul variants={fadeUp} className="mt-8 space-y-2.5 text-[0.95rem] text-ink">
              {['Predict - detect - simulate - optimize - explain', 'Every plan replayed and checked before you see it', 'Decision support only: you stay in control'].map((t) => (
                <li key={t} className="flex items-start gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-signal-green" aria-hidden />{t}</li>
              ))}
            </motion.ul>
          </div>

          {/* sign-in form (real authentication: the API checks the password and sets httpOnly cookies) */}
          <form className="p-8 lg:p-10" onSubmit={submit} noValidate aria-describedby={errText ? 'login-error' : undefined}>
            <motion.h2 variants={fadeUp} className="text-xl font-semibold">Sign in</motion.h2>
            <motion.p variants={fadeUp} className="mt-1 text-sm text-ink">
              Use the account your administrator created. Your role decides what you can do.
            </motion.p>
            {expired && !errText && (
              <motion.p variants={fadeUp} role="status" className="mt-4 rounded-xl border border-signal-amber/40 bg-signal-amber/10 px-3 py-2 text-sm text-ink">
                Your session ended. Sign in again.
              </motion.p>
            )}
            <motion.label variants={fadeUp} className="mt-6 block">
              <span className="text-sm font-medium text-ink">Email</span>
              <span className="relative mt-1.5 block">
                <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-dim" aria-hidden />
                <input className={field} type="email" autoComplete="username" required value={email}
                  onChange={(e) => setEmail(e.target.value)} placeholder="name@example.org" autoFocus />
              </span>
            </motion.label>
            <motion.label variants={fadeUp} className="mt-4 block">
              <span className="text-sm font-medium text-ink">Password</span>
              <span className="relative mt-1.5 block">
                <KeyRound className="pointer-events-none absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-dim" aria-hidden />
                <input className={field} type="password" autoComplete="current-password" required value={password}
                  onChange={(e) => setPassword(e.target.value)} />
              </span>
            </motion.label>
            {errText && (
              <p id="login-error" role="alert"
                className={cn('mt-4 flex items-start gap-2 rounded-xl border px-3 py-2 text-sm text-ink',
                  limited ? 'border-signal-amber/50 bg-signal-amber/10' : 'border-signal-red/50 bg-signal-red/10')}>
                <AlertTriangle className={cn('mt-0.5 h-4 w-4 shrink-0', limited ? 'text-signal-amber' : 'text-signal-red')} aria-hidden />
                {errText}
              </p>
            )}
            <motion.div variants={fadeUp} className="mt-8">
              <Button type="submit" variant="primary" size="lg" className="w-full" disabled={!email || !password}
                loading={login.isPending} success={welcome} icon={<ArrowRight className="h-5 w-5" aria-hidden />}>
                {welcome ? 'Welcome' : login.isPending ? 'Checking' : 'Enter control room'}
              </Button>
            </motion.div>
          </form>
        </motion.div>
      </main>
    </div>
  )
}
