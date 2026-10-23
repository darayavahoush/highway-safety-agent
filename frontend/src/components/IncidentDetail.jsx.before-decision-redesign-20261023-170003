import { useState } from 'react'
import { Check, Flag, Image as ImageIcon, Film, MousePointerClick, Sparkles } from 'lucide-react'
import PlateChip from './PlateChip.jsx'
import GoldenHourRing from './GoldenHourRing.jsx'
import ReasoningTrace from './ReasoningTrace.jsx'
import DispatchTimeline from './DispatchTimeline.jsx'
import { isLive } from '../api/client.js'
import {
  SEVERITY, STATUS_LABEL, TYPE_META, incidentTitle, locationLabel, fmtDuration,
} from '../lib/format.js'

const CLS_LABEL = { truck: 'Truck', bus: 'Bus', car: 'Car', van: 'Van', motorbike: 'Motorbike' }

export default function IncidentDetail({ incident, now, actions }) {
  const [isExplaining, setIsExplaining] = useState(false)
  if (!incident) {
    return (
      <div className="panel">
        <div className="empty">
          <MousePointerClick size={28} aria-hidden="true" />
          <p><b>Select an incident</b></p>
          <p>The agent’s briefing, reasoning, plates and dispatches show up here.</p>
        </div>
      </div>
    )
  }

  const sev = SEVERITY[incident.severity] || SEVERITY.P1
  const Icon = (TYPE_META[incident.type] || {}).icon
  const elapsed = now - incident.createdAt
  const hasEms = incident.dispatches.some((d) => d.target === 'EMS_108_AMBULANCE') || incident.type === 'IMPACT'
  const closed = ['resolved', 'false_alarm'].includes(incident.status)
  const base = `/evidence`

  return (
    <div className="panel detail">
      <div className="detail-head" style={{ '--sev': sev.color }}>
        <div className="detail-head-main">
          <span className="detail-icon">{Icon && <Icon size={20} aria-hidden="true" />}</span>
          <div>
            <h2>{incidentTitle(incident)}</h2>
            <p>{locationLabel(incident)}</p>
            <div className="detail-tags">
              <span className="sev" style={{ color: sev.color, borderColor: sev.color }}>{sev.label}</span>
              <span className={`chip chip--${incident.status}`}>{STATUS_LABEL[incident.status] || incident.status}</span>
              {incident.confidence != null && <span className="muted">{Math.round(incident.confidence * 100)}% confidence</span>}
            </div>
          </div>
        </div>
        {hasEms && !closed
          ? <GoldenHourRing elapsedMs={elapsed} />
          : <div className="elapsed"><b>{fmtDuration(elapsed)}</b><span>since detection</span></div>}
      </div>

      <div className="scroll detail-body">
        <section>
          <h3>Agent briefing</h3>
          {incident.briefing
            ? <p className="briefing">{incident.briefing}</p>
            : <p className="muted">The agent is still writing the briefing.</p>}
        </section>

        <section>
          <h3>Vehicles and plates</h3>
          <ul className="veh-list">
            {incident.vehicles.map((v) => (
              <li key={v.trackId} className="veh">
                <div>
                  <b>{CLS_LABEL[v.cls] || v.cls} #{v.trackId}</b>
                  <span>{Math.round(v.speedKmh)} km/h{v.lane ? `, ${v.lane.toLowerCase()}` : ''}</span>
                </div>
                <PlateChip plate={v.plate} />
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <h3>Agent reasoning</h3>
            {isLive && (
              <button
                type="button"
                className="btn btn--explain"
                disabled={isExplaining}
                onClick={async () => {
                  if (!incident || isExplaining) return
                  setIsExplaining(true)
                  try {
                    await fetch(`/api/incidents/${incident.id}/explain`, { method: 'POST' })
                  } catch (e) {
                    console.error('Explanation request error:', e)
                  } finally {
                    setIsExplaining(false)
                  }
                }}
                title="Request on-demand cognitive debriefing via Parallel AI"
              >
                <Sparkles size={12} className={isExplaining ? 'copilot-sparkle' : ''} />
                <span>{isExplaining ? 'Analyzing...' : 'Explain with AI'}</span>
              </button>
            )}
          </div>
          <ReasoningTrace incident={incident} />
        </section>

        <section>
          <h3>Dispatches</h3>
          <DispatchTimeline incident={incident} now={now} onCancel={actions.cancelDispatch} />
        </section>

        <section>
          <h3>Evidence</h3>
          <div className="evidence">
            <a className={`btn${isLive ? '' : ' btn--off'}`} href={isLive ? `${base}/snapshots/${incident.id}.jpg` : undefined}
               target="_blank" rel="noreferrer" aria-disabled={!isLive} title={isLive ? '' : 'Available with the live backend'}>
              <ImageIcon size={14} aria-hidden="true" />Snapshot
            </a>
            <a className={`btn${isLive ? '' : ' btn--off'}`} href={isLive ? `${base}/clips/${incident.id}.mp4` : undefined}
               target="_blank" rel="noreferrer" aria-disabled={!isLive} title={isLive ? '' : 'Available with the live backend'}>
              <Film size={14} aria-hidden="true" />10 s clip
            </a>
          </div>
        </section>
      </div>

      <div className="detail-foot">
        {incident.verdict ? (
          <p className="verdict">
            {incident.verdict === 'confirmed' ? <Check size={16} aria-hidden="true" /> : <Flag size={16} aria-hidden="true" />}
            Marked {incident.verdict === 'confirmed' ? 'as a real incident' : 'as a false alarm'}. This feeds back into rule tuning.
          </p>
        ) : (
          <>
            <span>Was this a real incident?</span>
            <button className="btn btn--ok" onClick={() => actions.sendFeedback(incident.id, 'confirmed')}>
              <Check size={14} aria-hidden="true" />Confirm
            </button>
            <button className="btn" onClick={() => actions.sendFeedback(incident.id, 'false_alarm')}>
              <Flag size={14} aria-hidden="true" />False alarm
            </button>
          </>
        )}
      </div>
    </div>
  )
}
