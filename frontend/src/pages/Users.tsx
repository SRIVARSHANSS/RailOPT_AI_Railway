// User Management (ADMIN, Phase 8): users, roles, deactivation, password resets, audit log.
// Everything comes from /api/admin/*; the API enforces the ADMIN role on every call.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { KeyRound, ScrollText, UserPlus, UserRoundCheck, UserRoundX } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { SignalBadge } from '../components/ui/Badges'
import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { Panel, PanelTitle } from '../components/ui/Panel'
import { SkeletonRows } from '../components/ui/Skeleton'
import { inputCls } from '../features/events/inputCls'
import { api, ApiError } from '../lib/api'
import { cn } from '../lib/cn'
import { staggerContainer } from '../lib/motion'
import { ROLE_LABEL, useSession, type Role } from '../store/session'
import { toast } from '../store/toast'

type AdminUser = { id: number; email: string; display_name: string; role: Role; is_active: boolean; last_login_at: string | null; created_at: string | null }
type AuditRow = { id: number; at: string; user_id: number | null; email: string | null; action: string; detail: Record<string, unknown>; ip: string | null }
type AuditPage = { total: number; limit: number; offset: number; actions: string[]; rows: AuditRow[] }

const ROLES: Role[] = ['ADMIN', 'CONTROLLER', 'ANALYST']
const PAGE = 25
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : 'never')
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : 'Request failed')

export function Users() {
  const me = useSession((s) => s.user)
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['admin-users'], queryFn: () => api<AdminUser[]>('/api/admin/users') })
  const [creating, setCreating] = useState(false)
  const [resetFor, setResetFor] = useState<AdminUser | null>(null)
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['admin-users'] })
    qc.invalidateQueries({ queryKey: ['admin-audit'] })
  }
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<AdminUser, 'role' | 'is_active'>> }) =>
      api<AdminUser>(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (u) => { refresh(); toast({ tone: 'success', title: 'User updated', description: `${u.email}: ${ROLE_LABEL[u.role]}, ${u.is_active ? 'active' : 'deactivated'}` }) },
    onError: (e) => toast({ tone: 'warning', title: 'Not changed', description: errMsg(e) }),
  })

  return (
    <motion.div className="mx-auto max-w-7xl space-y-6" variants={staggerContainer()} initial="hidden" animate="show">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-signal-cyan">Administration</p>
          <h1 className="text-3xl font-bold xl:text-4xl">User management</h1>
          <p className="mt-2 max-w-3xl text-ink-muted">
            Roles: <b className="text-ink">Controller</b> injects events, runs the optimizer and accepts or rejects plans;
            {' '}<b className="text-ink">Analyst</b> reads everything and runs what-ifs; <b className="text-ink">Admin</b> manages users and the network.
            Role changes, deactivation and password resets end that user's sessions at once.
          </p>
        </div>
        <Button variant="primary" icon={<UserPlus className="h-5 w-5" aria-hidden />} onClick={() => setCreating(true)}>New user</Button>
      </div>

      <Panel>
        <PanelTitle hint={users.data ? `${users.data.length} users` : undefined}>Users</PanelTitle>
        {users.isPending ? <SkeletonRows rows={4} /> : users.error ? <p className="text-signal-red">{errMsg(users.error)}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-ink-dim">
                <tr><th className="py-2 pr-3">User</th><th className="py-2 pr-3">Role</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Last sign-in</th><th className="py-2 text-right">Actions</th></tr>
              </thead>
              <tbody>
                {users.data.map((u) => {
                  const self = u.id === me?.id
                  return (
                    <tr key={u.id} className={cn('border-t border-line/10', !u.is_active && 'opacity-60')}>
                      <td className="py-2.5 pr-3"><span className="block font-medium text-ink">{u.display_name}{self && <span className="ml-2 text-xs text-ink-dim">(you)</span>}</span><span className="text-ink-muted">{u.email}</span></td>
                      <td className="py-2.5 pr-3">
                        <select aria-label={`Role of ${u.email}`} value={u.role} disabled={patch.isPending}
                          onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value as Role } })}
                          className={cn(inputCls, 'h-9 w-auto')}>
                          {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                        </select>
                      </td>
                      <td className="py-2.5 pr-3">{u.is_active ? <SignalBadge tone="success">Active</SignalBadge> : <SignalBadge tone="info">Deactivated</SignalBadge>}</td>
                      <td className="py-2.5 pr-3 text-ink-muted">{when(u.last_login_at)}</td>
                      <td className="py-2.5 text-right">
                        <div className="inline-flex flex-wrap justify-end gap-2">
                          <Button size="sm" variant="ghost" icon={<KeyRound className="h-4 w-4" aria-hidden />} onClick={() => setResetFor(u)}>Reset password</Button>
                          {u.is_active
                            ? <Button size="sm" variant="danger" icon={<UserRoundX className="h-4 w-4" aria-hidden />} disabled={patch.isPending}
                                onClick={() => patch.mutate({ id: u.id, body: { is_active: false } })}>Deactivate</Button>
                            : <Button size="sm" icon={<UserRoundCheck className="h-4 w-4" aria-hidden />} disabled={patch.isPending}
                                onClick={() => patch.mutate({ id: u.id, body: { is_active: true } })}>Reactivate</Button>}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <AuditLog />
      <CreateUser open={creating} onOpenChange={setCreating} onDone={refresh} />
      <ResetPassword user={resetFor} onClose={() => setResetFor(null)} onDone={refresh} />
    </motion.div>
  )
}

function CreateUser({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => void }) {
  const [form, setForm] = useState({ email: '', display_name: '', role: 'CONTROLLER' as Role, password: '' })
  const create = useMutation({
    mutationFn: () => api<AdminUser>('/api/admin/users', { method: 'POST', body: JSON.stringify(form) }),
    onSuccess: (u) => {
      onDone()
      onOpenChange(false)
      setForm({ email: '', display_name: '', role: 'CONTROLLER', password: '' })
      toast({ tone: 'success', title: 'User created', description: `${u.email} (${ROLE_LABEL[u.role]})` })
    },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate() }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New user" description="Give the person their password through a separate channel.">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">Name<input className={cn(inputCls, 'mt-1')} required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
        <label className="block text-sm">Email<input className={cn(inputCls, 'mt-1')} type="email" required autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label className="block text-sm">Role
          <select className={cn(inputCls, 'mt-1')} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </label>
        <label className="block text-sm">Initial password (at least 10 characters)
          <input className={cn(inputCls, 'mt-1')} type="password" required minLength={10} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {create.error && <p role="alert" className="text-sm text-signal-red">{errMsg(create.error)}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" variant="primary" loading={create.isPending}>Create user</Button>
        </div>
      </form>
    </Dialog>
  )
}

function ResetPassword({ user, onClose, onDone }: { user: AdminUser | null; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const reset = useMutation({
    mutationFn: () => api<AdminUser>(`/api/admin/users/${user?.id}/password`, { method: 'POST', body: JSON.stringify({ password }) }),
    onSuccess: (u) => {
      setPassword('')
      onDone()
      onClose()
      toast({ tone: 'success', title: 'Password reset', description: `${u.email}: every session of this user has ended.` })
    },
  })
  return (
    <Dialog open={user !== null} onOpenChange={(o) => { if (!o) { setPassword(''); reset.reset(); onClose() } }}
      title="Reset password" description={user ? `New password for ${user.email}. Their open sessions end.` : undefined}>
      <form onSubmit={(e) => { e.preventDefault(); reset.mutate() }} className="space-y-3">
        <label className="block text-sm">New password (at least 10 characters)
          <input className={cn(inputCls, 'mt-1')} type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {reset.error && <p role="alert" className="text-sm text-signal-red">{errMsg(reset.error)}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={reset.isPending}>Set password</Button>
        </div>
      </form>
    </Dialog>
  )
}

function AuditLog() {
  const [action, setAction] = useState('')
  const [email, setEmail] = useState('')
  const [offset, setOffset] = useState(0)
  const q = new URLSearchParams({ limit: String(PAGE), offset: String(offset), ...(action && { action }), ...(email && { email }) })
  const log = useQuery({ queryKey: ['admin-audit', action, email, offset], queryFn: () => api<AuditPage>(`/api/admin/audit?${q}`),
    placeholderData: keepPreviousData })
  const total = log.data?.total ?? 0
  return (
    <Panel>
      <PanelTitle hint={log.data ? `${total} entries` : undefined}><span className="inline-flex items-center gap-2"><ScrollText className="h-5 w-5 text-signal-cyan" aria-hidden />Audit log</span></PanelTitle>
      <div className="mb-4 flex flex-wrap gap-3">
        <select aria-label="Filter by action" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0) }} className={cn(inputCls, 'w-auto')}>
          <option value="">All actions</option>
          {(log.data?.actions ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <input aria-label="Filter by user email" placeholder="User email contains..." value={email}
          onChange={(e) => { setEmail(e.target.value); setOffset(0) }} className={cn(inputCls, 'w-64')} />
      </div>
      {log.isPending ? <SkeletonRows rows={5} /> : log.error ? <p className="text-signal-red">{errMsg(log.error)}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-ink-dim">
              <tr><th className="py-2 pr-3">When</th><th className="py-2 pr-3">Who</th><th className="py-2 pr-3">Action</th><th className="py-2">Detail</th></tr>
            </thead>
            <tbody>
              {log.data.rows.map((r) => (
                <tr key={r.id} className="border-t border-line/10 align-top">
                  <td className="whitespace-nowrap py-2 pr-3 text-ink-muted">{when(r.at)}</td>
                  <td className="py-2 pr-3 text-ink">{r.email ?? '-'}</td>
                  <td className="py-2 pr-3"><span className={cn('rounded-md px-1.5 py-0.5 font-mono text-xs',
                    r.action.includes('FAILED') || r.action.includes('RATE') || r.action.includes('REJECTED') ? 'bg-signal-red/15 text-signal-red' : 'bg-white/[0.06] text-ink')}>{r.action}</span></td>
                  <td className="py-2 font-mono text-xs text-ink-muted"><span className="line-clamp-2 break-all">{JSON.stringify(r.detail)}</span></td>
                </tr>
              ))}
              {log.data.rows.length === 0 && <tr><td colSpan={4} className="py-4 text-ink-muted">No entries.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-4 flex items-center justify-between text-sm text-ink-muted">
        <span>{total ? `${offset + 1}-${Math.min(offset + PAGE, total)} of ${total}` : ''}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</Button>
          <Button size="sm" variant="ghost" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Older</Button>
        </div>
      </div>
    </Panel>
  )
}
