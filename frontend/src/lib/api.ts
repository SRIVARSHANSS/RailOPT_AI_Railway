// Thin client for the RailOpt API (FastAPI, port 8000). Responses carry their own data_label.
// Phase 8: the session is in httpOnly cookies, so every request sends credentials. A 401 on a
// normal request triggers one silent refresh (POST /api/auth/refresh) and a retry; if that fails
// the user is signed out ("session expired").
import { useSession } from '../store/session'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

let refreshing: Promise<boolean> | null = null

/** One refresh at a time, shared by every request that hit a 401. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_URL}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => { window.setTimeout(() => { refreshing = null }, 0) })
  return refreshing
}

function message(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message)
  return `Request failed (${status})`
}

export async function api<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await res.json().catch(() => null)
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    if (!retried && (await refreshSession())) return api<T>(path, init, true)
    useSession.getState().signedOut(true)
  }
  if (!res.ok) throw new ApiError(res.status, message(res.status, body), body)
  return body as T
}

export type Health = { data_label: 'SIMULATED' | 'REAL' | 'HYPOTHETICAL on a real recorded day'; status: string; timetable: string }

export type NetworkSummary = {
  data_label: 'SIMULATED'
  timetable: string
  stations: { code: string; name: string; km: number }[]
  sections: { section_id: string; tracks: number; status: string }[]
  trains: { train_id: string; train_type: string; priority: number }[]
}
