// What each role may do in the UI. This only hides or disables controls; the API enforces the
// same rules on every request (backend app/core/auth.py, tests/test_auth.py permission matrix).
import { ROLE_LABEL, useSession, type Role } from '../store/session'

export type Action = 'control' | 'whatif' | 'admin'

const ALLOWED: Record<Action, Role[]> = {
  control: ['CONTROLLER'], // events, optimize, accept / reject, scenario reset
  whatif: ['CONTROLLER', 'ANALYST'],
  admin: ['ADMIN'], // users, audit log, network management
}

export function can(role: Role | undefined, action: Action): boolean {
  return !!role && ALLOWED[action].includes(role)
}

/** { ok, reason }: reason is a tooltip for a disabled control. */
export function useCan(action: Action): { ok: boolean; reason: string | undefined } {
  const role = useSession((s) => s.user?.role)
  const ok = can(role, action)
  const need = ALLOWED[action].map((r) => ROLE_LABEL[r]).join(' or ')
  return { ok, reason: ok ? undefined : `Needs the ${need} role${role ? ` (you are ${ROLE_LABEL[role]})` : ''}` }
}
