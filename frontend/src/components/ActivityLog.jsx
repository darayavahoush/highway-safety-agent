import { useMemo } from 'react'
import { BellOff } from 'lucide-react'
import { EmptyState, SkeletonRows, OfflineState } from './StateBlock.jsx'
import { targetMeta, fmtClock, incidentTitle } from '../lib/format.js'
import { isProblem, problemLabel } from '../lib/dispatch.js'

const STATE_TEXT = { queued: 'Queued', sent: 'Sent', acknowledged: 'Acknowledged', cancelled: 'Cancelled' }

export default function ActivityLog({ list, onSelect, conn }) {
  const rows = useMemo(
    () => list
      .flatMap((i) => i.dispatches.map((d) => ({ d, i })))
      .sort((a, b) => (b.d.queuedAt ?? 0) - (a.d.queuedAt ?? 0))
      .slice(0, 30),
    [list],
  )
  const tally = rows.reduce((t, { d }) => { const k = isProblem(d) ? 'problem' : d.status; return { ...t, [k]: (t[k] || 0) + 1 } }, {})
  return (
    <div className="panel activity">
      <div className="panel-head">
        <h2>Dispatch activity</h2>
        <span className="stage-meta">{rows.length} recent</span>
      </div>
      {rows.length > 0 && (
        <div className="act-summary" aria-label="Alert summary">
          <span><b>{rows.length}</b> alerts</span>
          {['problem', 'acknowledged', 'sent', 'queued', 'cancelled'].filter((k) => tally[k]).map((k) => (
            <span key={k} className={`chip chip--${k}`}>{tally[k]} {k === 'problem' ? 'failed or not confirmed' : STATE_TEXT[k].toLowerCase()}</span>
          ))}
        </div>
      )}
      <div className="scroll">
        {rows.length === 0 && list.length === 0 && conn === 'connecting' && <SkeletonRows label="Loading alerts" />}
        {rows.length === 0 && list.length === 0 && conn === 'offline' && <OfflineState what="alerts" />}
        {rows.length === 0 && !(list.length === 0 && (conn === 'connecting' || conn === 'offline')) && (
          <EmptyState icon={BellOff} title="No alerts sent yet" tight>
            When the system warns drivers or calls a patrol, each message is listed here.
          </EmptyState>
        )}
        {rows.map(({ d, i }) => {
          const meta = targetMeta(d.target)
          const Icon = meta.icon
          return (
            <button key={d.id} className="act" onClick={() => onSelect(i.id)}>
              <time>{fmtClock(d.sentAt ?? d.queuedAt)}</time>
              <span className="act-target"><Icon size={14} aria-hidden="true" />{meta.label}</span>
              <span className="act-msg">{d.message || incidentTitle(i)}</span>
              <span className={`chip chip--${isProblem(d) ? 'problem' : d.status}`}>{isProblem(d) ? problemLabel(d.status) : STATE_TEXT[d.status]}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
