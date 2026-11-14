// Demo session (real auth arrives in Phase 8). Persisted per browser when storage works.
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type Role = 'controller' | 'analyst' | 'admin'

export const ROLE_LABEL: Record<Role, string> = {
  controller: 'Controller',
  analyst: 'Analyst',
  admin: 'Admin',
}

type SessionState = {
  role: Role | null
  sidebarCollapsed: boolean
  signIn: (role: Role) => void
  signOut: () => void
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
      role: null,
      sidebarCollapsed: false,
      signIn: (role) => set({ role }),
      signOut: () => set({ role: null }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: 'railopt-session', storage: safeStorage },
  ),
)
