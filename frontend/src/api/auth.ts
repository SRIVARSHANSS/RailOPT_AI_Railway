// Auth calls (Phase 8): the API sets / clears httpOnly cookies; the UI only mirrors the user.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, ApiError } from '../lib/api'
import { useSession, type User } from '../store/session'

/** On app start: ask the API who is signed in (cookie), refreshing the session once if needed. */
export function useBootstrapSession() {
  const status = useSession((s) => s.status)
  useEffect(() => {
    if (status !== 'unknown') return
    const { setUser, signedOut } = useSession.getState()
    api<User>('/api/auth/me')
      .then(setUser)
      .catch(async (e) => {
        if (e instanceof ApiError && e.status === 401) {
          try {
            setUser(await api<User>('/api/auth/refresh', { method: 'POST' }))
            return
          } catch { /* not signed in */ }
        }
        signedOut(false)
      })
  }, [status])
}

export function useLogin() {
  const setUser = useSession((s) => s.setUser)
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { email: string; password: string }) =>
      api<User>('/api/auth/login', { method: 'POST', body: JSON.stringify(args) }),
    onSuccess: (u) => {
      qc.clear() // nothing cached from another user's session
      setUser(u)
    },
  })
}

export function useLogout() {
  const signedOut = useSession((s) => s.signedOut)
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api<{ signed_out: boolean }>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      qc.clear()
      signedOut(false)
    },
  })
}
