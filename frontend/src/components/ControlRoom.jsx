import { ShieldCheck, Siren, Eye, ArrowRight, Wifi, Lightbulb } from 'lucide-react'
import IncidentQueue from './IncidentQueue.jsx'
import LiveStage from './LiveStage.jsx'
import ActivityLog from './ActivityLog.jsx'
import IncidentDetail from './IncidentDetail.jsx'
import StatsStrip from './StatsStrip.jsx'
import { isActive, incidentTitle, locationLabel, fmtAge, SEVERITY } from '../lib/format.js'
import { SEVERITY_HELP, whyItMatters, nextStep, sceneFor } from '../lib/plain.js'

const CONN = {
  demo: 'Demo simulation',
  live: 'Live connection',
  connecting: 'Connecting…',
  offline: 'Offline, retrying',
}

const RANK = { P0: 0, P1: 1, P2: 2 }

export default function ControlRoom({
  state, list, selected, now, actions, filter, setFilter, camera, today,
}) {
  const active = list.filter(isActive)
  const top = [...active].sort(
    (a, b) => (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3) || b.createdAt - a.createdAt,
  )[0]
  const critical = active.filter((i) => i.severity === 'P0').length
  const tone = active.length === 0 ? 'clear' : critical > 0 ? 'critical' : 'watch'
  const road = camera ? `${camera.highway || 'the highway'}${camera.km ? `, KM ${camera.km}` : ''}` : 'the highway'
  const n = active.length

  const headline = tone === 'clear'
    ? 'All clear'
    : `${n} incident${n === 1 ? '' : 's'} need${n === 1 ? 's' : ''} attention`

  return (
    <div className="cr" data-scene={sceneFor(now)} data-tone={tone}>
      <div className="cr-backdrop" aria-hidden="true" />

      <section className="cr-hero" aria-live="polite">
        <div className="cr-hero-main">
          <span className="cr-kicker">
            <Wifi size={13} aria-hidden="true" />
            {CONN[state.conn] || CONN.connecting}
            <i aria-hidden="true">·</i>
            Watching {road}
          </span>
          <h2 className="cr-headline">
            {tone === 'clear'
              ? <ShieldCheck size={38} aria-hidden="true" />
              : <Siren size={38} aria-hidden="true" />}
            <span>{headline}</span>
          </h2>
          {tone === 'clear' ? (
            <p className="cr-sub">Nothing needs you right now. New incidents appear here the moment the camera spots one.</p>
          ) : (
            <p className="cr-sub">
              <span><b>{incidentTitle(top)}</b>, {locationLabel(top)}. First seen {fmtAge(now - top.createdAt)}.</span>
              <button type="button" className="cr-open" onClick={() => actions.select(top.id)}>
                Open it <ArrowRight size={15} aria-hidden="true" />
              </button>
            </p>
          )}
        </div>

        <div className="cr-glance" role="group" aria-label="At a glance">
          <div><b>{n}</b><span>Open now</span></div>
          <div><b>{today}</b><span>Seen today</span></div>
          <div>
            <b>{state.metrics?.detectToDispatchS != null ? `${state.metrics.detectToDispatchS.toFixed(1)}s` : '–'}</b>
            <span>Spot to alert</span>
          </div>
        </div>

        <ul className="cr-legend" aria-label="What the severity labels mean">
          {SEVERITY_HELP.map(([key, label, meaning]) => (
            <li key={key} style={{ '--sev': SEVERITY[key].color }}>
              <i aria-hidden="true" /><b>{label}</b><span>{meaning}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="cr-grid">
        <section className="cr-col cr-col--list">
          <h3 className="cr-step"><em>01</em>What is happening</h3>
          <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
            now={now} filter={filter} setFilter={setFilter} />
        </section>

        <section className="cr-col cr-col--stage">
          <h3 className="cr-step"><em>02</em>Where it is</h3>
          <LiveStage incident={selected} camera={camera} metrics={state.metrics}
            incidents={list} onSelectIncident={actions.select} />
          <ActivityLog list={list} onSelect={actions.select} />
        </section>

        <section className="cr-col cr-col--detail">
          <h3 className="cr-step"><em>03</em>What to do</h3>
          {selected && (
            <div className="cr-guide" style={{ '--sev': (SEVERITY[selected.severity] || SEVERITY.P1).color }}>
              <Lightbulb size={16} aria-hidden="true" />
              <div>
                <p><b>Why it matters.</b> {whyItMatters(selected.type)}</p>
                <p><b>Your next step.</b> {nextStep(selected)}</p>
              </div>
            </div>
          )}
          <IncidentDetail incident={selected} now={now} actions={actions} />
        </section>
      </div>

      <details className="cr-tech">
        <summary><Eye size={14} aria-hidden="true" />Technical performance <span>for engineers</span></summary>
        <StatsStrip metrics={state.metrics} open={n} today={today} blackspots={state.blackspots} camera={camera} />
      </details>
    </div>
  )
}
