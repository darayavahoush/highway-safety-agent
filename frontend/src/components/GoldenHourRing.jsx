import { fmtDuration } from '../lib/format.js'

const TOTAL = 60 * 60 * 1000

export default function GoldenHourRing({ elapsedMs, size = 92 }) {
  const p = Math.min(1, elapsedMs / TOTAL)
  const r = size / 2 - 7
  const c = 2 * Math.PI * r
  const color = p < 0.34 ? 'var(--green)' : p < 0.67 ? 'var(--amber)' : 'var(--red)'
  return (
    <div className="ring" style={{ width: size, height: size }} title="Time since detection, out of the 60-minute golden hour">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="6" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(p, 0.015))}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-label">
        <b>{fmtDuration(elapsedMs)}</b>
        <span>golden hour</span>
      </div>
    </div>
  )
}
