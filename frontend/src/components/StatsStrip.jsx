function Stat({ value, unit, label }) {
  return (
    <div className="stat">
      <div className="stat-num"><b>{value ?? '–'}</b>{value != null && unit && <span>{unit}</span>}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export default function StatsStrip({ metrics, open, today, blackspots, camera }) {
  const max = Math.max(1, ...blackspots.map((b) => b.count))
  const here = camera ? Math.floor(camera.km) : null
  return (
    <footer className="stats">
      <div className="stats-grid">
        <Stat value={metrics?.fps} unit="fps" label="Edge tracker speed" />
        <Stat value={metrics?.ruleMs} unit="ms" label="Rule engine per frame" />
        <Stat value={metrics ? (metrics.agentLatencyMs / 1000).toFixed(1) : null} unit="s" label="Agent briefing time" />
        <Stat value={metrics?.detectToDispatchS != null ? metrics.detectToDispatchS.toFixed(1) : null} unit="s" label="Detection to first dispatch" />
        <Stat value={open} label="Open incidents" />
        <Stat value={today} label="Incidents today" />
      </div>
      {blackspots.length > 0 && (
        <div className="blackspots">
          <div className="bs-bars" role="img" aria-label="Past incidents by kilometre marker">
            {blackspots.map((b) => (
              <div key={b.km} className={`bs-col${b.km === here ? ' bs-col--here' : ''}`} title={`KM ${b.km}: ${b.count} incidents`}>
                <i style={{ height: `${Math.max(8, (b.count / max) * 100)}%` }} />
                <span>{b.km}</span>
              </div>
            ))}
          </div>
          <div className="stat-label">Past incidents by kilometre marker on {camera?.highway || 'this highway'}</div>
        </div>
      )}
    </footer>
  )
}
