import { useReducedMotion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { loginMedia } from '../../config/media'

const WIDE = '(min-width: 769px)'

function useMatch(query: string) {
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

/** Login background: video -> drifting poster image -> CSS night corridor.
 *  The video is never requested on phones or with reduced motion; it fades in
 *  only once it can play through, over the poster. */
export function LoginHero() {
  const reduce = useReducedMotion()
  const wide = useMatch(WIDE)
  const [videoReady, setVideoReady] = useState(false)
  const useVideo = Boolean(loginMedia.video) && wide && !reduce

  return (
    <div aria-hidden className="fixed inset-0 -z-10 overflow-hidden bg-canvas-0">
      {loginMedia.poster ? (
        <img src={loginMedia.poster} alt="" decoding="async"
          className={`absolute inset-0 h-full w-full object-cover ${reduce ? '' : 'animate-hero-drift'} will-change-transform`} />
      ) : (
        <NightCorridor />
      )}
      {useVideo && (
        <video src={loginMedia.video ?? undefined} poster={loginMedia.poster ?? undefined} autoPlay muted loop playsInline preload="auto"
          onCanPlayThrough={() => setVideoReady(true)}
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${videoReady ? 'opacity-100' : 'opacity-0'}`} />
      )}
      {/* scrim: strong on the left where the card sits, plus an overall darkening */}
      <div className="absolute inset-0 bg-gradient-to-r from-canvas-0/95 via-canvas-0/70 to-canvas-0/30" />
      <div className="absolute inset-0 bg-gradient-to-t from-canvas-0/90 via-transparent to-canvas-0/40" />
    </div>
  )
}

/** CSS-only fallback until real media exists: converging rails, signal lights and light trails. */
function NightCorridor() {
  return (
    <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_75%_60%,rgb(var(--c-canvas-2))_0%,rgb(var(--c-canvas-0))_70%)]">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="rail" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="rgb(34 211 238)" stopOpacity="0.55" />
            <stop offset="1" stopColor="rgb(34 211 238)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* two tracks converging to a vanishing point on the right */}
        {[
          'M 640 900 L 1150 360', 'M 760 900 L 1162 360',
          'M 960 900 L 1186 360', 'M 1080 900 L 1198 360',
        ].map((d) => <path key={d} d={d} stroke="url(#rail)" strokeWidth="2" fill="none" />)}
        {/* signals */}
        {[
          [1010, 520, 'rgb(52 211 153)'], [1120, 420, 'rgb(52 211 153)'], [1250, 560, 'rgb(251 191 36)'], [1205, 450, 'rgb(52 211 153)'],
        ].map(([x, y, c]) => (
          <g key={`${x}`}>
            <line x1={x} y1={(y as number) + 6} x2={x} y2={(y as number) + 60} stroke="rgb(148 178 220)" strokeOpacity="0.25" />
            <circle cx={x} cy={y} r="24" fill={c as string} opacity="0.12" />
            <circle cx={x} cy={y} r="11" fill={c as string} opacity="0.3" />
            <circle cx={x} cy={y} r="4.5" fill={c as string} />
          </g>
        ))}
      </svg>
      {/* light trails moving along the corridor (transform only) */}
      <div className="absolute left-[38%] top-[40%] h-[2px] w-[40%] origin-left rotate-[-46deg]">
        <div className="animate-streak h-full w-40 rounded-full bg-gradient-to-r from-transparent via-signal-cyan to-white shadow-[0_0_16px_3px_rgb(var(--c-cyan)/0.7)]" />
      </div>
      <div className="absolute left-[56%] top-[48%] h-[2px] w-[34%] origin-left rotate-[-60deg]">
        <div className="animate-streak h-full w-32 rounded-full bg-gradient-to-r from-transparent via-signal-amber to-white [animation-delay:-3.2s]" />
      </div>
    </div>
  )
}
