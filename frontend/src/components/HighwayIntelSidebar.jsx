import {
  Activity, ArrowRight, Camera, CarFront, CheckCircle2, CloudRain, Compass,
  Gauge, MapPinned, Radio, Route, ShieldCheck, Signpost, Truck,
} from 'lucide-react'
import RegionalWeather from './RegionalWeather.jsx'

const PAGE_GUIDE = {
  control: { eyebrow: 'COMMAND CENTRE', title: 'Start with the signal', body: 'Scan active incidents first, inspect the selected event, then review the camera and response context.', next: 'Open Corridor Map to explore the wider road environment.' },
  corridor: { eyebrow: 'ROAD NETWORK', title: 'Read the terrain', body: 'Choose a highway on the map, then click a point to see the weather there.', next: 'Click an incident marker to see the nearest trauma hospital and the drive time.' },
  incidents: { eyebrow: 'EVENT REVIEW', title: 'Triage with context', body: 'Filter the queue, select an incident, and compare severity with location and supporting details.', next: 'Return to Overview when you need the overall operational picture.' },
  activity: { eyebrow: 'DISPATCH HISTORY', title: 'Follow the response', body: 'Use the timeline to understand what happened, when it happened, and which incident each action belongs to.', next: 'Select an event to connect its history to the incident record.' },
  system: { eyebrow: 'SERVICE HEALTH', title: 'Check the signals', body: 'Review connection status, camera health, tracker rate, and event totals reported by the app.', next: 'A missing metric means it was not reported; it does not prove service health.' },
}

function connectionText(conn) {
  if (conn === 'live') return 'LIVE FEED'
  if (conn === 'demo') return 'DEMO MODE'
  if (conn === 'offline') return 'OFFLINE'
  return 'CONNECTING'
}

export default function HighwayIntelSidebar({
  page, onNavigate, incidents = [], activeCount = 0, conn = 'unknown',
  metrics, camera, corridorOverview,
}) {
  const active = corridorOverview || null
  const highway = active?.highway || camera?.highway || 'NH 16'
  const stretch = active?.name || [camera?.section, camera?.name].filter(Boolean).join(' · ') || 'Amaravati – Vijayawada – Guntur'
  const districts = active?.districts?.length ? active.districts.join(' · ') : 'NTR · Guntur'
  const blackspots = active?.blackspots ?? 255
  const coordinates = active?.weatherCoordinates || [
    Number(camera?.lng ?? camera?.longitude ?? 80.60),
    Number(camera?.lat ?? camera?.latitude ?? 16.45),
  ]
  const locationName = active?.weatherName || stretch
  const guide = PAGE_GUIDE[page] || PAGE_GUIDE.control

  return (
    <aside className="highway-intel-sidebar" aria-label="Highway intelligence sidebar">
      <section className="hrap-rail-hero">
        <div className="hrap-rail-hero-copy">
          <span className="hrap-rail-eyebrow"><Route size={12} /> HIGHWAY INTELLIGENCE / AP</span>
          <h2>Road watch</h2>
          <p>One place for corridor context, current conditions, and operational status.</p>
        </div>
        <div className="hrap-rail-vehicle-strip" aria-hidden="true"><CarFront size={18} /><span className="hrap-rail-vehicle-lane" /><Truck size={19} /><span className="hrap-rail-vehicle-label">VEHICLE FLOW / ROAD WATCH</span></div>
        <div className="hrap-rail-hero-foot">
          <span><MapPinned size={12} /> Andhra Pradesh network</span>
          <span>FIELD VIEW</span>
        </div>
      </section>

      <section className="hrap-rail-corridor" aria-label="Corridor overview">
        <div className="hrap-rail-section-top">
          <span className="hrap-rail-section-label"><Compass size={13} /> CORRIDOR OVERVIEW</span>
          <span className="hrap-rail-terrain"><span /> 3D MAP</span>
        </div>
        <div className="hrap-rail-route-title"><strong>{highway}</strong><span>{active?.id ? 'SELECTED' : 'REFERENCE'}</span></div>
        <h3>{stretch}</h3>
        <div className="hrap-rail-corridor-facts">
          <div><span>Districts</span><strong>{districts}</strong></div>
          <div><span>Listed blackspots</span><strong>{blackspots}</strong></div>
          <div><span>Map view</span><strong>3D, Andhra Pradesh only</strong></div>
        </div>
        {active?.terrainError && <p className="hrap-rail-terrain-error">{active.terrainError}</p>}
        <button type="button" className="hrap-rail-map-cta" onClick={() => onNavigate('corridor')}>
          Open road map <ArrowRight size={14} />
        </button>
        {!active && <p className="hrap-rail-hint">The selected corridor details update when the map is opened.</p>}
      </section>

      <section className="hrap-rail-status" aria-label="System and incident summary">
        <div className="hrap-rail-status-head">
          <span className="hrap-rail-section-label"><Activity size={13} /> SYSTEM PULSE</span>
          <span className={`hrap-rail-connection hrap-status-${conn}`}><i /> {connectionText(conn)}</span>
        </div>
        <div className="hrap-rail-metrics">
          <div className="hrap-rail-metric"><span className="hrap-rail-metric-icon"><ShieldCheck size={15} /></span><span className="hrap-rail-metric-label">Active incidents</span><strong>{activeCount}</strong></div>
          <div className="hrap-rail-metric"><span className="hrap-rail-metric-icon"><Activity size={15} /></span><span className="hrap-rail-metric-label">Total incidents</span><strong>{incidents.length}</strong></div>
          <div className="hrap-rail-metric"><span className="hrap-rail-metric-icon"><Gauge size={15} /></span><span className="hrap-rail-metric-label">Tracker rate</span><strong>{metrics?.fps == null ? '—' : `${metrics.fps} fps`}</strong></div>
          <div className="hrap-rail-metric"><span className="hrap-rail-metric-icon"><Camera size={15} /></span><span className="hrap-rail-metric-label">Camera link</span><strong>{camera ? 'Assigned' : 'Pending'}</strong></div>
        </div>
      </section>

      <section className="hrap-rail-weather">
        <div className="hrap-rail-weather-title">
          <span className="hrap-rail-section-label"><CloudRain size={13} /> WEATHER & ROAD RISK</span>
          <span className="hrap-rail-live-label"><i /> FORECAST</span>
        </div>
        <RegionalWeather coordinates={coordinates} locationName={locationName} />
      </section>

      <section className="hrap-rail-navigation">
        <span className="hrap-rail-section-label"><Signpost size={14} /> SITE NAVIGATION · OPEN A SECTION</span>
        <div className="hrap-rail-nav-list">
          {[
            ['control', 'Overview', 'Network snapshot and active incidents'],
            ['corridor', 'Corridor map', 'Road routes, terrain and weather'],
            ['incidents', 'Incidents', 'Find and triage road incidents'],
            ['activity', 'Activity', 'Response and dispatch history'],
            ['system', 'System status', 'Connection, camera and tracker health'],
          ].map(([key, label, detail], index) => (
            <button key={key} type="button" className={`hrap-rail-nav-item${page === key ? ' is-current' : ''}`}
              aria-current={page === key ? 'page' : undefined} title={`Open ${label}: ${detail}`} onClick={() => onNavigate(key)}>
              <span className="hrap-rail-nav-number">0{index + 1}</span>
              <span className="hrap-rail-nav-copy"><strong>{label}</strong><small>{detail}</small></span>
              {page === key ? <CheckCircle2 size={14} /> : <ArrowRight size={14} />}
            </button>
          ))}
        </div>
      </section>

      <section className="hrap-rail-guide">
        <span className="hrap-rail-section-label">{guide.eyebrow} / HOW TO USE</span>
        <h3>{guide.title}</h3>
        <p>{guide.body}</p>
        <div className="hrap-rail-next"><ArrowRight size={13} /><span>{guide.next}</span></div>
      </section>

      <div className="hrap-rail-advisory">
        <Radio size={15} />
        <div><strong>Decision-support notice</strong><p>Weather is a forecast, not a roadside sensor. Confirm hazards using authorised sources before dispatch decisions.</p></div>
      </div>
      <div className="hrap-rail-footer"><span>HRAP / FIELD INTELLIGENCE</span><span>2026</span></div>
    </aside>
  )
}
