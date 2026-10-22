import { useMemo } from 'react'
import { targetMeta, fmtClock, incidentTitle } from '../lib/format.js'

const STATE_TEXT = { queued: 'Queued', sent: 'Sent', acknowledged: 'Acknowledged', cancelled: 'Cancelled' }

export default function ActivityLog({ list, onSelect }) {
  const rows = useMemo(
    () => list
      .flatMap((i) => i.dispatches.map((d) => ({ d, i })))
      .sort((a, b) => (b.d.queuedAt ?? 0) - (a.d.queuedAt ?? 0))
      .slice(0, 30),
    [list],
  )
  return (
    <div className="panel activity">
      <div className="panel-head">
        <h2>Dispatch activity</h2>
        <span className="stage-meta">{rows.length} recent</span>
      </div>
      <div className="scroll">
        {rows.length === 0 && <div className="empty empty--tight"><p>No dispatches yet today.</p></div>}
        {rows.map(({ d, i }) => {
          const meta = targetMeta(d.target)
          const Icon = meta.icon
          return (
            <button key={d.id} className="act" onClick={() => onSelect(i.id)}>
              <time>{fmtClock(d.sentAt ?? d.queuedAt)}</time>
              <span className="act-target"><Icon size={14} aria-hidden="true" />{meta.label}</span>
              <span className="act-msg">{d.message || incidentTitle(i)}</span>
              <span className={`chip chip--${d.status}`}>{STATE_TEXT[d.status] || d.status}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
