import { Eye, X } from 'lucide-react'
import { targetMeta, fmtClock, fmtOffset } from '../lib/format.js'
import { isProblem, problemText } from '../lib/dispatch.js'

function Row({ d, incident, now, onCancel }) {
  const meta = targetMeta(d.target)
  const Icon = meta.icon
  const t0 = incident.createdAt
  let status
  let time = ''
  if (d.status === 'queued') {
    const left = Math.max(0, Math.ceil(((d.cancelUntil ?? now) - now) / 1000))
    status = `Goes out in ${left} s unless an operator cancels`
    time = `${left} s`
  } else if (d.status === 'sent') {
    status = 'Sent, waiting for acknowledgement'
    time = fmtOffset((d.sentAt ?? now) - t0)
  } else if (d.status === 'acknowledged') {
    status = `Acknowledged ${fmtOffset((d.ackAt ?? now) - t0)} after detection`
    time = fmtOffset((d.sentAt ?? now) - t0)
  } else if (d.status === 'cancelled') {
    status = 'Cancelled by operator'
  } else {
    status = problemText(d.status)
  }
  const isVms = d.target === 'VARIABLE_MESSAGE_SIGN_VMS'
  return (
    <li className={`disp disp--${isProblem(d) ? 'problem' : d.status}`}>
      <span className="disp-icon"><Icon size={16} aria-hidden="true" /></span>
      <div className="disp-main">
        <div className="disp-title">{meta.label}</div>
        <div className="disp-meta">{status}</div>
        {d.message && (isVms ? <div className="vms">{d.message}</div> : <div className="disp-msg">{d.message}</div>)}
        {meta.endpoint && <div className="disp-endpoint">POST {meta.endpoint}</div>}
        {d.status === 'queued' && (
          <button className="btn btn--danger" onClick={() => onCancel(incident.id, d.id)}>
            <X size={14} aria-hidden="true" />Cancel dispatch
          </button>
        )}
      </div>
      <span className="disp-time">{time}</span>
    </li>
  )
}

export default function DispatchTimeline({ incident, now, onCancel }) {
  return (
    <ol className="disp-list">
      <li className="disp disp--acknowledged">
        <span className="disp-icon"><Eye size={16} aria-hidden="true" /></span>
        <div className="disp-main">
          <div className="disp-title">Detected by edge tracker</div>
          <div className="disp-meta">{fmtClock(incident.createdAt)} IST</div>
        </div>
        <span className="disp-time">+0.0 s</span>
      </li>
      {incident.dispatches.map((d) => (
        <Row key={d.id} d={d} incident={incident} now={now} onCancel={onCancel} />
      ))}
      {incident.dispatches.length === 0 && (
        <li className="muted disp-wait">Waiting for the agent’s decision.</li>
      )}
    </ol>
  )
}
