import { useEffect, useMemo, useRef } from 'react'

const W = 900
const H = 280
const LANE_Y = { eSlow: 52, eFast: 96, wFast: 184, wSlow: 228 }
const SIZE = { truck: [78, 24], bus: [72, 24], van: [48, 20], car: [38, 18], motorbike: [22, 9] }
const BODY = { truck: '#7F95AB', bus: '#B59A5B', van: '#8CA3B5', car: '#98B0C6', motorbike: '#C4D2DF' }
const K = 0.9 // pixels per (km/h * second), purely visual

function mulberry(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function ambientTraffic() {
  const r = mulberry(42)
  const lanes = [
    [LANE_Y.eSlow, 1], [LANE_Y.eFast, 1], [LANE_Y.wFast, -1], [LANE_Y.wSlow, -1],
  ]
  const classes = ['car', 'car', 'car', 'truck', 'van', 'motorbike', 'bus', 'truck']
  return Array.from({ length: 16 }, (_, i) => {
    const [y, dir] = lanes[i % 4]
    return {
      id: `a${i}`, x0: r() * W, y, dir,
      speed: 52 + r() * 36, cls: classes[Math.floor(r() * classes.length)], involved: false,
    }
  })
}

const laneY = (v) => (v.laneIndex === 1 ? LANE_Y.eFast : LANE_Y.eSlow)

function Vehicle({ item, accent }) {
  const [w, h] = SIZE[item.cls] || SIZE.car
  const fill = item.involved ? BODY[item.cls] || BODY.car : '#41586F'
  return (
    <g data-vid={item.id} data-x0={item.x0} data-y={item.y} data-dir={item.dir} data-speed={item.speed}
       transform={`translate(${item.x0} ${item.y})`}>
      <g transform={item.dir < 0 ? 'scale(-1 1)' : undefined}>
        <rect x={-w / 2 + 2} y={-h / 2 + 3} width={w} height={h} rx="4" fill="rgba(0,0,0,.35)" />
        <rect x={-w / 2} y={-h / 2} width={w} height={h} rx="4" fill={fill}
              stroke={item.involved ? accent : 'none'} strokeWidth={item.involved ? 2 : 0} />
        <rect x={w / 2 - Math.min(14, w * 0.3)} y={-h / 2 + 2.5} width={Math.min(9, w * 0.2)} height={h - 5} rx="2" fill="rgba(15,24,34,.55)" />
      </g>
      {item.involved && (
        <g>
          <rect x={-34} y={-h / 2 - 24} width={68} height={17} rx="8" fill="rgba(15,24,34,.9)" stroke={accent} strokeWidth="1" />
          <text x="0" y={-h / 2 - 12} textAnchor="middle" fontSize="11" fontFamily="IBM Plex Sans, sans-serif" fill="#E9EFF5">{item.label}</text>
        </g>
      )}
    </g>
  )
}

export default function LaneMap({ incident, camera }) {
  const svgRef = useRef(null)
  const accent = incident?.severity === 'P0' ? '#F0525B' : incident?.severity === 'P2' ? '#5AA8F0' : '#F4B63F'

  const items = useMemo(() => {
    const ambient = ambientTraffic()
    const involved = (incident?.vehicles || []).map((v) => ({
      id: `v${v.trackId}`, x0: (v.x ?? 0.5) * W, y: laneY(v), dir: v.dir ?? 1,
      speed: v.speedKmh || 0, cls: v.cls, involved: true, label: `#${v.trackId}`,
    }))
    // keep ambient traffic out of the involved vehicles' lane band so the incident stays readable
    const free = ambient.filter((a) => !involved.some((v) => Math.abs(a.y - v.y) < 1 && Math.abs(a.x0 - v.x0) < 160))
    return { ambient: free, involved }
  }, [incident?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return undefined
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const nodes = Array.from(svg.querySelectorAll('[data-vid]'))
    const span = W + 160
    let raf
    const t0 = performance.now()
    const tick = (now) => {
      const t = (now - t0) / 1000
      nodes.forEach((n) => {
        const x0 = +n.dataset.x0, y = +n.dataset.y, dir = +n.dataset.dir, speed = +n.dataset.speed
        const x = reduce || speed === 0 ? x0 : ((((x0 + 80 + dir * speed * K * t) % span) + span) % span) - 80
        n.setAttribute('transform', `translate(${x.toFixed(1)} ${y})`)
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [items])

  const blocked = incident && ['STALLED_VEHICLE', 'IMPACT'].includes(incident.type)
  const lead = items.involved[0]
  const bandY = lead ? lead.y - 22 : 0
  const impact = incident?.type === 'IMPACT' && items.involved.length >= 2
    ? [(items.involved[0].x0 + items.involved[1].x0) / 2, items.involved[0].y]
    : null

  return (
    <svg ref={svgRef} className="lanemap" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img"
         aria-label="Top-down lane view of the selected incident">
      <rect width={W} height={H} fill="#16202B" />
      <rect y="14" width={W} height="252" fill="#2A3A4A" />
      <rect y="118" width={W} height="44" fill="#1C3A33" />
      <path d={`M0 140H${W}`} stroke="#2B5A4C" strokeWidth="1" strokeDasharray="3 9" />
      {[30, 118, 162, 250].map((y) => <path key={y} d={`M0 ${y}H${W}`} stroke="#DCE6EF" strokeWidth="2" opacity=".85" />)}
      {[74, 206].map((y) => <path key={y} d={`M0 ${y}H${W}`} stroke="#DCE6EF" strokeWidth="2" strokeDasharray="22 18" opacity=".55" />)}
      <text x="16" y="144" fontSize="12" fill="#8FB3A6" fontFamily="IBM Plex Sans, sans-serif">Towards {camera?.towards || 'north'}, eastbound lanes above</text>
      <text x={W - 16} y="144" textAnchor="end" fontSize="12" fill="#8FB3A6" fontFamily="IBM Plex Sans, sans-serif">Towards {camera?.opposite || 'south'}, westbound lanes below</text>

      {blocked && lead && (
        <g>
          <rect x="0" y={bandY} width={W} height="44" fill="rgba(240,82,91,.13)" />
          <rect x={Math.max(8, lead.x0 - 130)} y={bandY + 2} width="260" height="40" rx="6" fill="none"
                stroke="#F0525B" strokeWidth="1.5" strokeDasharray="6 5" />
        </g>
      )}

      {items.ambient.map((a) => <Vehicle key={a.id} item={a} accent={accent} />)}
      {items.involved.map((v) => <Vehicle key={v.id} item={v} accent={accent} />)}

      {impact && (
        <g transform={`translate(${impact[0]} ${impact[1]})`}>
          <polygon points="0,-20 5,-7 18,-12 9,-1 20,6 7,7 6,20 -1,10 -12,18 -8,6 -20,2 -8,-3 -14,-15 -3,-9"
                   fill="#F0525B" opacity=".9" />
        </g>
      )}
    </svg>
  )
}
