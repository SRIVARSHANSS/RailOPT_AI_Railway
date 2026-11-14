// Simulation clock (display time). Railway state always comes from the API for that minute.
import { create } from 'zustand'
import type { OptimizeResult } from '../api/types'

export type Speed = 1 | 10 | 60

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

export const useSim = create<SimState>()((set, get) => ({
  minute: 9 * 60 + 55,
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
}))

/** Real milliseconds one simulated minute lasts at a speed (1x = real time). */
export const minuteMs = (speed: Speed) => 60000 / speed

// Console UI state shared across pages: the alert the user selected, the last optimizer run.
export type Highlight = { section_id: string | null; trains: string[]; key: string } | null

type ConsoleState = {
  highlight: Highlight
  setHighlight: (h: Highlight) => void
  optimize: OptimizeResult | null
  decided: Record<string, 'accept' | 'reject'>
  setOptimize: (r: OptimizeResult | null) => void
  markDecided: (id: string, d: 'accept' | 'reject') => void
}

export const useConsole = create<ConsoleState>()((set) => ({
  highlight: null,
  setHighlight: (highlight) => set({ highlight }),
  optimize: null,
  decided: {},
  setOptimize: (optimize) => set({ optimize }),
  markDecided: (id, d) => set((s) => ({ decided: { ...s.decided, [id]: d } })),
}))
