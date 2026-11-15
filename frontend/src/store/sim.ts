// Simulation clock (display time) and console UI state. Railway state always comes from the API.
// Clock, speed and the last optimizer result survive a page refresh (sessionStorage, per tab);
// `playing` always restores as paused.
import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'
import type { OptimizeResult } from '../api/types'

export type Speed = 1 | 10 | 60

export const DEMO_START = 9 * 60 + 55

/** sessionStorage can throw (privacy modes, blocked storage): fall back to memory. */
const sessionSafe = createJSONStorage((): StateStorage => {
  try {
    const probe = '__railopt_probe__'
    window.sessionStorage.setItem(probe, '1')
    window.sessionStorage.removeItem(probe)
    return window.sessionStorage
  } catch {
    const mem = new Map<string, string>()
    return {
      getItem: (k) => mem.get(k) ?? null,
      setItem: (k, v) => void mem.set(k, v),
      removeItem: (k) => void mem.delete(k),
    }
  }
})

type SimState = {
  minute: number
  playing: boolean
  speed: Speed
  range: [number, number]
  minuteStartedAt: number // performance.now() when the current minute began (for glides)
  setMinute: (m: number) => void // a jump: trains snap
  advance: () => void // +1 minute while playing: trains glide
  setPlaying: (p: boolean) => void
  setSpeed: (s: Speed) => void
  setRange: (r: [number, number]) => void
}

const clamp = (m: number, [lo, hi]: [number, number]) => Math.min(hi, Math.max(lo, m))

export const useSim = create<SimState>()(
  persist(
    (set, get) => ({
      minute: DEMO_START,
      playing: false,
      speed: 60,
      range: [9 * 60 + 28, 11 * 60 + 26],
      minuteStartedAt: 0,
      setMinute: (m) => set({ minute: clamp(Math.round(m), get().range), minuteStartedAt: performance.now() }),
      advance: () => {
        const { minute, range } = get()
        if (minute >= range[1]) return set({ playing: false })
        set({ minute: minute + 1, minuteStartedAt: performance.now() })
      },
      setPlaying: (playing) => set({ playing, minuteStartedAt: performance.now() }),
      setSpeed: (speed) => set({ speed, minuteStartedAt: performance.now() }),
      setRange: (range) => set({ range, minute: clamp(get().minute, range) }),
    }),
    { name: 'railopt-sim', storage: sessionSafe, partialize: (s) => ({ minute: s.minute, speed: s.speed }) },
  ),
)

/** Real milliseconds one simulated minute lasts at a speed (1x = real time). */
export const minuteMs = (speed: Speed) => 60000 / speed

// Console UI state shared across pages: the alert the user selected, the last optimizer run.
// The optimizer result is cached with the scenario_version it was computed against; when the API
// reports another version (restart, reset, event, a decision made elsewhere) the cache is dropped.
export type Highlight = { section_id: string | null; trains: string[]; key: string } | null

type ConsoleState = {
  highlight: Highlight
  setHighlight: (h: Highlight) => void
  optimize: OptimizeResult | null
  decided: Record<string, 'accept' | 'reject'>
  version: string | null // scenario_version the cached optimize/decided belong to
  setOptimize: (r: OptimizeResult | null) => void
  adoptVersion: (v: string) => void // after this tab's own decision: the cache still applies
  syncVersion: (v: string) => void // a server version seen in any response
  markDecided: (id: string, d: 'accept' | 'reject') => void
  clear: () => void
}

export const useConsole = create<ConsoleState>()(
  persist(
    (set) => ({
      highlight: null,
      setHighlight: (highlight) => set({ highlight }),
      optimize: null,
      decided: {},
      version: null,
      setOptimize: (optimize) => set({ optimize, version: optimize?.scenario_version ?? null }),
      adoptVersion: (version) => set({ version }),
      syncVersion: (v) => set((s) => {
        if (s.version === v || (!s.optimize && !Object.keys(s.decided).length)) return s.version === v ? s : { version: v }
        const recSelected = s.highlight?.key.startsWith('rec-')
        return { optimize: null, decided: {}, version: v, ...(recSelected ? { highlight: null } : {}) }
      }),
      markDecided: (id, d) => set((s) => ({ decided: { ...s.decided, [id]: d } })),
      clear: () => set({ highlight: null, optimize: null, decided: {}, version: null }),
    }),
    { name: 'railopt-console', storage: sessionSafe, partialize: (s) => ({ optimize: s.optimize, decided: s.decided, version: s.version }) },
  ),
)
