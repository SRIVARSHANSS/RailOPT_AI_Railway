import * as RadioGroup from '@radix-ui/react-radio-group'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, BarChart3, Check, Radio, ShieldCheck, TrainFront } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { LoginHero } from '../components/layout/LoginHero'
import { SimulatedBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { cn } from '../lib/cn'
import { duration, ease, fadeUp, spring, staggerContainer } from '../lib/motion'
import { useSession, type Role } from '../store/session'

const ROLES: { value: Role; title: string; text: string; icon: ReactNode }[] = [
  { value: 'controller', title: 'Controller', text: 'Watch the corridor, review conflicts, accept or reject plans.', icon: <Radio className="h-5 w-5" /> },
  { value: 'analyst', title: 'Analyst', text: 'Compare strategies, read model cards and explanations.', icon: <BarChart3 className="h-5 w-5" /> },
  { value: 'admin', title: 'Admin', text: 'Manage scenarios and the demo set-up.', icon: <ShieldCheck className="h-5 w-5" /> },
]

export function Login() {
  const signIn = useSession((s) => s.signIn)
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const [role, setRole] = useState<Role>('controller')
  const [phase, setPhase] = useState<'idle' | 'loading' | 'success'>('idle')

  const enter = () => {
    setPhase('loading')
    // short, honest pause: the demo login has nothing to verify
    window.setTimeout(() => setPhase('success'), reduce ? 0 : 450)
    window.setTimeout(() => {
      signIn(role)
      navigate('/dashboard')
    }, reduce ? 0 : 900)
  }

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

          {/* role picker */}
          <div className="p-8 lg:p-10">
            <motion.h2 variants={fadeUp} id="role-label" className="text-xl font-semibold">Choose a role</motion.h2>
            <motion.p variants={fadeUp} className="mt-1 text-sm text-ink">Demo login - real authentication arrives in Phase 8.</motion.p>
            <RadioGroup.Root value={role} onValueChange={(v) => setRole(v as Role)} aria-labelledby="role-label" className="mt-6 space-y-3">
              {ROLES.map((r) => {
                const active = role === r.value
                return (
                  <motion.div key={r.value} variants={fadeUp}>
                    <RadioGroup.Item value={r.value}
                      // ARIA radio pattern: arrow-key focus also selects
                      onFocus={(e) => e.currentTarget.matches(':focus-visible') && setRole(r.value)}
                      className={cn('group relative flex w-full items-start gap-4 rounded-2xl border p-4 text-left transition-colors',
                        active ? 'border-signal-cyan/60 bg-signal-cyan/10' : 'border-white/15 bg-white/[0.03] hover:border-white/30 hover:bg-white/[0.05]')}>
                      {active && <motion.span layoutId="role-glow" transition={spring.snappy} aria-hidden
                        className="absolute inset-0 rounded-2xl shadow-[0_0_0_1px_rgb(var(--c-cyan)/0.5),0_10px_40px_-12px_rgb(var(--c-cyan)/0.6)]" />}
                      <span className={cn('relative grid h-10 w-10 shrink-0 place-items-center rounded-xl', active ? 'bg-signal-cyan text-canvas-0' : 'bg-canvas-0/50 text-ink')}>{r.icon}</span>
                      <span className="relative min-w-0 flex-1">
                        <span className="block font-semibold">{r.title}</span>
                        <span className="mt-0.5 block text-sm text-ink">{r.text}</span>
                      </span>
                      <span aria-hidden className={cn('relative mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full border', active ? 'border-signal-cyan bg-signal-cyan' : 'border-line/40')}>
                        <RadioGroup.Indicator asChild>
                          <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: duration.fast, ease: ease.out }}>
                            <Check className="h-3 w-3 text-canvas-0" strokeWidth={3} />
                          </motion.span>
                        </RadioGroup.Indicator>
                      </span>
                    </RadioGroup.Item>
                  </motion.div>
                )
              })}
            </RadioGroup.Root>
            <motion.div variants={fadeUp} className="mt-8">
              <Button variant="primary" size="lg" className="w-full" onClick={enter}
                loading={phase === 'loading'} success={phase === 'success'} icon={<ArrowRight className="h-5 w-5" aria-hidden />}>
                {phase === 'success' ? 'Welcome' : phase === 'loading' ? 'Opening control room' : 'Enter control room'}
              </Button>
            </motion.div>
          </div>
        </motion.div>
      </main>
    </div>
  )
}
