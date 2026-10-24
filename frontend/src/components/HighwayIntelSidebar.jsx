import {
  ArrowRight, CheckCircle2, CloudRain, LayoutDashboard, Map as MapIcon, Siren, History, HeartPulse, Radio,
} from 'lucide-react'
import RegionalWeather from './RegionalWeather.jsx'

const NAV = [
  ['control', 'Overview', 'What needs attention now', LayoutDashboard],
  ['corridor', 'Road map', 'Highways in 3D, weather, hospitals', MapIcon],
  ['incidents', 'Incidents', 'Every incident and what to do', Siren],
  ['activity', 'Activity', 'Who was alerted, and when', History],
  ['system', 'System status', 'Is everything working?', HeartPulse],
]

const HELP = {
  control: 'Start with the biggest card at the top. It tells you what happened and what to do next.',
  corridor: 'Pick a highway above the map, then click anywhere on it to see the weather there.',
  incidents: 'Choose an incident on the left to see what happened and what the agent already did.',
  activity: 'Each row is one alert sent to a patrol, ambulance, police team or road sign.',
  system: 'Green means working. Amber means worth checking. Grey means not reported yet.',
}

const CONN = { live: 'Live', demo: 'Demo', offline: 'Offline', connecting: 'Connecting' }

export default function HighwayIntelSidebar({
  page, onNavigate, incidents = [], activeCount = 0, conn = 'unknown', camera, corridorOverview,
}) {
  const active = corridorOverview || null
  const highway = active?.highway || camera?.highway || 'NH-16'
  const stretch = active?.name || [camera?.section, camera?.name].filter(Boolean).join(' · ') || 'Amaravati – Vijayawada – Guntur'
  const blackspots = active?.blackspots
  const coordinates = active?.weatherCoordinates || [
    Number(camera?.lng ?? camera?.longitude ?? 80.60),
    Number(camera?.lat ?? camera?.latitude ?? 16.45),
  ]
  const locationName = active?.weatherName || stretch

  return (
    <aside className="highway-intel-sidebar rail" aria-label="Site navigation and road conditions">
      <section className="rail-hero">
        <span className="rail-eyebrow">Andhra Pradesh · Highway watch</span>
        <h2>Road watch</h2>
        <p>Cameras watch the road. The agent alerts the right people. You decide.</p>
        <div className="rail-chips">
          <span className={`rail-chip rail-chip--${conn}`}><i />{CONN[conn] || 'Connecting'}</span>
          <span className={`rail-chip ${activeCount ? 'rail-chip--warn' : 'rail-chip--ok'}`}>
            {activeCount ? `${activeCount} open now` : 'All clear'}
          </span>
        </div>
      </section>

      <nav className="rail-nav" aria-label="Pages">
        <h3>Go to</h3>
        {NAV.map(([key, label, detail, Icon]) => (
          <button key={key} type="button" className={`rail-nav-item${page === key ? ' is-current' : ''}`}
            aria-current={page === key ? 'page' : undefined} onClick={() => onNavigate(key)}>
            <span className="rail-nav-icon"><Icon size={17} aria-hidden="true" /></span>
            <span className="rail-nav-copy"><strong>{label}</strong><small>{detail}</small></span>
            {page === key ? <CheckCircle2 size={15} aria-hidden="true" /> : <ArrowRight size={15} aria-hidden="true" />}
          </button>
        ))}
      </nav>

      <section className="rail-road" aria-label="Selected road">
        <span className="rail-label">Selected road</span>
        <div className="rail-road-title"><strong>{highway}</strong>{blackspots != null && <em>{blackspots} accident spots</em>}</div>
        <p>{stretch}</p>
        {active?.terrainError && <p className="rail-error">{active.terrainError}</p>}
        <button type="button" className="rail-cta" onClick={() => onNavigate('corridor')}>
          Open the 3D road map <ArrowRight size={14} aria-hidden="true" />
        </button>
      </section>

      <section className="hrap-rail-weather">
        <div className="hrap-rail-weather-title">
          <span className="hrap-rail-section-label"><CloudRain size={13} /> WEATHER &amp; ROAD RISK</span>
          <span className="hrap-rail-live-label"><i /> FORECAST</span>
        </div>
        <RegionalWeather coordinates={coordinates} locationName={locationName} />
      </section>

      <details className="rail-help">
        <summary>How to use this page</summary>
        <p>{HELP[page] || HELP.control}</p>
        <p className="rail-note"><Radio size={13} aria-hidden="true" /> Weather is a forecast, not a roadside sensor. Confirm hazards with official sources before sending help.</p>
      </details>

      <div className="rail-foot"><span>HRAP · 2026</span><span>{incidents.length} incidents on record</span></div>
    </aside>
  )
}
