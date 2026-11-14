import { Pause, Play, RotateCcw } from 'lucide-react'
import { cn } from '../../lib/cn'
import { fmt } from '../../lib/time'
import { useSim, type Speed } from '../../store/sim'
import { Tooltip } from '../../components/ui/Tooltip'

const SPEEDS: Speed[] = [1, 10, 60]

/** Play / pause, speed and a scrubber. Scrubbing is a jump: trains snap. */
export function ClockBar({ resetTo }: { resetTo: number }) {
  const { minute, playing, speed, range, setMinute, setPlaying, setSpeed } = useSim()
  return (
    <div className="glass flex flex-wrap items-center gap-4 px-4 py-3">
      <button
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause simulation' : 'Play simulation'}
        className={cn('grid h-12 w-12 place-items-center rounded-xl transition-shadow',
          playing ? 'bg-signal-amber text-canvas-0' : 'bg-signal-cyan text-canvas-0 shadow-glow')}
      >
        {playing ? <Pause className="h-5 w-5" aria-hidden /> : <Play className="h-5 w-5 translate-x-px" aria-hidden />}
      </button>

      <div className="min-w-[6.5rem]">
        <div className="text-xs uppercase tracking-wider text-ink-dim">Sim time</div>
        <div className="font-mono text-3xl font-semibold tabular" aria-live="off">{fmt(minute)}</div>
      </div>

      <div role="radiogroup" aria-label="Simulation speed" className="flex rounded-xl border border-line/15 bg-canvas-0/40 p-1">
        {SPEEDS.map((s) => (
          <button key={s} role="radio" aria-checked={speed === s} onClick={() => setSpeed(s)}
            className={cn('rounded-lg px-3 py-1.5 font-mono text-sm', speed === s ? 'bg-surface-raised text-ink' : 'text-ink-muted hover:text-ink')}>
            {s}x
          </button>
        ))}
      </div>

      <label className="flex min-w-[12rem] flex-1 items-center gap-3">
        <span className="font-mono text-sm text-ink-dim">{fmt(range[0])}</span>
        <input type="range" min={range[0]} max={range[1]} step={1} value={minute}
          onChange={(e) => setMinute(Number(e.target.value))}
          aria-label="Scrub simulation time" aria-valuetext={fmt(minute)}
          className="h-2 flex-1 cursor-pointer accent-[rgb(var(--c-cyan))]" />
        <span className="font-mono text-sm text-ink-dim">{fmt(range[1])}</span>
      </label>

      <Tooltip content={`Jump to ${fmt(resetTo)}`}>
        <button onClick={() => { setPlaying(false); setMinute(resetTo) }} aria-label={`Jump to ${fmt(resetTo)}`}
          className="rounded-xl p-2.5 text-ink-muted hover:bg-white/5 hover:text-ink">
          <RotateCcw className="h-5 w-5" aria-hidden />
        </button>
      </Tooltip>
    </div>
  )
}
