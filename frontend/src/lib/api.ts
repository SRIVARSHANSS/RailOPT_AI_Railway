// Thin client for the RailOpt API (FastAPI, port 8000). Every response is SIMULATED data.
export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
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
