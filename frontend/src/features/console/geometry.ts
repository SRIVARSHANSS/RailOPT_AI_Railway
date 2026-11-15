// Map geometry (drawing only). Stations sit at their real km; sections are SVG paths.
// Train motion between two API states is sampled ALONG these paths (getPointAtLength),
// and a change of section always passes through the station node.
import type { Network, Section, TrainState } from '../../api/types'

export const VIEW = { w: 1200, h: 340 }
export const MAIN_Y = 120
const LANE = 13
const X0 = 95
const X1 = 1105

export type StationGeo = { code: string; name: string; x: number; y: number; platforms: number; lift: number }
export type SectionGeo = Section & { lanes: string[]; alternate: boolean; labelX: number; labelY: number; showLabel: boolean }
export type Geometry = { stations: Record<string, StationGeo>; sections: Record<string, SectionGeo> }

export function buildGeometry(net: Network): Geometry {
  const maxKm = Math.max(...net.stations.map((s) => s.km))
  const stations: Record<string, StationGeo> = {}
  for (const s of net.stations) {
    stations[s.code] = { code: s.code, name: s.name, x: X0 + (s.km / maxKm) * (X1 - X0), y: MAIN_Y, platforms: s.platforms, lift: 0 }
  }
  // stations closer than a label's width (e.g. KON and MDU, 3.75 km apart): lift every other label
  const byX = Object.values(stations).sort((a, b) => a.x - b.x)
  for (let i = 1; i < byX.length; i++) {
    if (byX[i].x - byX[i - 1].x < 130 && byX[i - 1].lift === 0) byX[i].lift = -48
  }
  const sections: Record<string, SectionGeo> = {}
  for (const sec of net.sections) {
    const a = stations[sec.from_station]
    const b = stations[sec.to_station]
    const parallel = net.sections.some((o) => o !== sec && o.from_station === sec.from_station && o.to_station === sec.to_station)
    const alternate = parallel && sec.status !== 'open'
    let lanes: string[]
    if (alternate) {
      // standby line drawn as a separate curve below the main line
      const dip = 130
      lanes = [`M ${a.x} ${a.y} C ${a.x + 70} ${a.y + dip}, ${b.x - 70} ${b.y + dip}, ${b.x} ${b.y}`]
    } else if (sec.tracks > 1) {
      lanes = [-LANE, LANE].slice(0, sec.tracks).map(
        (off) => `M ${a.x} ${a.y} L ${a.x + 34} ${a.y + off} L ${b.x - 34} ${b.y + off} L ${b.x} ${b.y}`,
      )
    } else {
      lanes = [`M ${a.x} ${a.y} L ${b.x} ${b.y}`]
    }
    sections[sec.section_id] = {
      ...sec, lanes, alternate, showLabel: Math.abs(b.x - a.x) >= 90,
      // single-track labels sit below the line near the far end, clear of train labels
      labelX: !alternate && sec.tracks === 1 ? a.x + (b.x - a.x) * 0.84 : (a.x + b.x) / 2,
      labelY: alternate ? a.y + 122 : sec.tracks > 1 ? a.y - 56 : a.y + 34,
    }
  }
  return { stations, sections }
}

/** Stable lane per train on multi-track sections (so a train never hops lanes mid-section). */
export const laneOf = (sec: SectionGeo, t: Pick<TrainState, 'priority'>) => (sec.lanes.length > 1 ? (t.priority === 2 ? 1 : 0) : 0)

// ---- path sampling via a hidden SVG (getPointAtLength needs a real path element) ----
let host: SVGSVGElement | null = null
const cache = new Map<string, { el: SVGPathElement; len: number }>()

function pathInfo(d: string) {
  let hit = cache.get(d)
  if (hit) return hit
  if (!host) {
    host = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    host.setAttribute('aria-hidden', 'true')
    host.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden'
    document.body.appendChild(host)
  }
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'path')
  el.setAttribute('d', d)
  host.appendChild(el)
  hit = { el, len: el.getTotalLength() }
  cache.set(d, hit)
  return hit
}

export type Pt = { x: number; y: number }

export function pointOnPath(d: string, p: number): Pt {
  const { el, len } = pathInfo(d)
  const q = el.getPointAtLength(Math.min(1, Math.max(0, p)) * len)
  return { x: q.x, y: q.y }
}

export function angleOnPath(d: string, p: number): number {
  const a = pointOnPath(d, Math.max(0, p - 0.01))
  const b = pointOnPath(d, Math.min(1, p + 0.01))
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI
}

function samplePath(d: string, p0: number, p1: number): Pt[] {
  const { len } = pathInfo(d)
  const n = Math.max(2, Math.ceil((Math.abs(p1 - p0) * len) / 4))
  return Array.from({ length: n + 1 }, (_, i) => pointOnPath(d, p0 + ((p1 - p0) * i) / n))
}

// ---- where a train is drawn for one API state --------------------------------------
export type Anchor =
  | { kind: 'path'; d: string; p: number; section: string }
  | { kind: 'point'; x: number; y: number; station: string }

export const SIGNAL_OFFSET = 24 // the red exit signal is drawn this far ahead of a waiting train

export function anchorOf(t: TrainState, geo: Geometry): Anchor | null {
  if (t.status === 'not_started') return null
  if (t.status === 'in_section') {
    const sec = geo.sections[t.location]
    if (!sec) return null
    return { kind: 'path', d: sec.lanes[laneOf(sec, t)], p: t.progress ?? 0, section: sec.section_id }
  }
  const st = geo.stations[t.location]
  if (!st) return null
  return { kind: 'point', x: st.x, y: st.y, station: st.code }
}

export function anchorPoint(a: Anchor): Pt {
  return a.kind === 'path' ? pointOnPath(a.d, a.p) : { x: a.x, y: a.y }
}

export function anchorAngle(a: Anchor): number {
  return a.kind === 'path' ? angleOnPath(a.d, a.p) : 0
}

/** Route between two consecutive API states, as points along the track.
 *  Same section: along the path. Different: to the end of the old section, through the
 *  station node, then along the new section. Never a straight line across the map. */
export function routeBetween(from: Anchor, to: Anchor, geo: Geometry): Pt[] {
  if (from.kind === 'path' && to.kind === 'path' && from.d === to.d) return samplePath(from.d, from.p, Math.max(from.p, to.p))
  const pts: Pt[] = []
  if (from.kind === 'path') pts.push(...samplePath(from.d, from.p, 1))
  else pts.push({ x: from.x, y: from.y })
  if (to.kind === 'path') {
    const node = geo.stations[geo.sections[to.section].from_station]
    pts.push({ x: node.x, y: node.y })
    pts.push(...samplePath(to.d, 0, to.p))
  } else {
    pts.push({ x: to.x, y: to.y })
  }
  return pts
}

/** Constant-speed position + heading at fraction f of a polyline. */
export function along(pts: Pt[], cum: number[], f: number): { x: number; y: number; angle: number } {
  const total = cum[cum.length - 1]
  if (total === 0) return { ...pts[pts.length - 1], angle: 0 }
  const target = f * total
  let i = 1
  while (i < cum.length - 1 && cum[i] < target) i++
  const seg = cum[i] - cum[i - 1] || 1
  const t = (target - cum[i - 1]) / seg
  const a = pts[i - 1]
  const b = pts[i]
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI }
}

export function cumulative(pts: Pt[]): number[] {
  const out = [0]
  for (let i = 1; i < pts.length; i++) out.push(out[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y))
  return out
}
