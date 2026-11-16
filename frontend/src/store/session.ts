// Signed-in user (Phase 8). The session itself lives in httpOnly cookies set by the API; this
// store only mirrors GET /api/auth/me for the UI. The role is never trusted from storage: the API
// checks it on every request. Only the sidebar preference is persisted.
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type Role = 'ADMIN' | 'CONTROLLER' | 'ANALYST'
export type User = { id: number | null; email: string; display_name: string; role: Role }

export const ROLE_LABEL: Record<Role, string> = {
  CONTROLLER: 'Controller',
  ANALYST: 'Analyst',
  ADMIN: 'Admin',
}

type SessionState = {
  user: User | null
  status: 'unknown' | 'signed-in' | 'signed-out'
  expired: boolean // the session ended by itself (not a sign-out)
  sidebarCollapsed: boolean
  setUser: (u: User) => void
  signedOut: (expired?: boolean) => void
  toggleSidebar: () => void
}

// localStorage can throw (private mode, blocked storage): fall back to memory.
const safeStorage = createJSONStorage(() => {
  try {
    const probe = '__railopt_probe__'
    window.localStorage.setItem(probe, '1')
    window.localStorage.removeItem(probe)
    return window.localStorage
  } catch {
    const mem = new Map<string, string>()
    return {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    }
  }
})

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      user: null,
      status: 'unknown',
      expired: false,
      sidebarCollapsed: false,
      setUser: (user) => set({ user, status: 'signed-in', expired: false }),
      signedOut: (expired = false) => set({ user: null, status: 'signed-out', expired }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: 'railopt-session', storage: safeStorage, partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }) },
  ),
)
