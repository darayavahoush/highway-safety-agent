import { ShieldCheck, Inbox } from 'lucide-react'
import {
  TYPE_META, SEVERITY, STATUS_LABEL, isActive, incidentTitle, locationLabel, fmtAge,
  incidentWhy, vehicleSummary,
} from '../lib/format.js'
import { EmptyState, SkeletonRows, OfflineState } from './StateBlock.jsx'

export default function IncidentQueue({ list, selectedId, onSelect, now, filter, setFilter, conn }) {
  const active = list.filter(isActive)
  const shown = filter === 'active' ? active : list
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Incidents</h2>
        <div className="seg" role="tablist" aria-label="Incident filter">
          <button role="tab" aria-selected={filter === 'active'} onClick={() => setFilter('active')}>Active {active.length}</button>
          <button role="tab" aria-selected={filter === 'all'} onClick={() => setFilter('all')}>All {list.length}</button>
        </div>
      </div>
      <div className="scroll">
        {list.length === 0 && conn === 'connecting' && <SkeletonRows label="Loading incidents" />}
        {list.length === 0 && conn === 'offline' && <OfflineState what="incidents" />}
        {shown.length === 0 && list.length > 0 && (
          <EmptyState icon={ShieldCheck} title="No active incidents">
            Everything so far has been dealt with. Switch to “All” to see past incidents.
          </EmptyState>
        )}
        {list.length === 0 && conn !== 'connecting' && conn !== 'offline' && (
          <EmptyState icon={Inbox} title="Nothing here yet">
            The tracker is watching the road. New incidents appear here the moment a rule fires.
          </EmptyState>
        )}
        {shown.map((i) => {
          const sev = SEVERITY[i.severity] || SEVERITY.P1
          const Icon = (TYPE_META[i.type] || {}).icon
          const fresh = now - i.createdAt < 4000
          const plate = i.vehicles?.find((v) => v.plate)?.plate
          const why = incidentWhy(i)
          const veh = vehicleSummary(i)
          return (
            <button
              key={i.id}
              className={`inc${isActive(i) ? ' inc--active' : ''}${i.severity === 'P0' ? ' inc--p0' : ''}${fresh ? ' inc--new' : ''}`}
              style={{ '--sev': sev.color }}
              aria-current={i.id === selectedId}
              onClick={() => onSelect(i.id)}
            >
              <span className="inc-icon">{Icon && <Icon size={18} aria-hidden="true" />}</span>
              <span className="inc-body">
                <span className="inc-row">
                  <span className="inc-title">{incidentTitle(i)}</span>
                  <span className="inc-sev" style={{ color: sev.color }}>{sev.label}</span>
                </span>
                {why && <span className="inc-why" title={why}>{why}</span>}
                <span className="inc-row inc-sub">
                  <span>{locationLabel(i)}</span>
                  <span>{fmtAge(now - i.createdAt)}</span>
                </span>
                <span className="inc-row">
                  <span className={`chip chip--${i.status}`}>{STATUS_LABEL[i.status] || i.status}</span>
                  {(veh || plate) && (
                    <span className="inc-tags">
                      {veh && <span className="inc-veh">{veh}</span>}
                      {plate && <span className="inc-plate">{plate.text}</span>}
                    </span>
                  )}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
