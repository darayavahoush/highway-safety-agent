import { useState, useEffect } from 'react'
import useControlRoom from './state/useControlRoom.js'
import TopBar from './components/TopBar.jsx'
import Home from './components/Home.jsx'
import IncidentQueue from './components/IncidentQueue.jsx'
import LiveStage from './components/LiveStage.jsx'
import ActivityLog from './components/ActivityLog.jsx'
import IncidentDetail from './components/IncidentDetail.jsx'
import StatsStrip from './components/StatsStrip.jsx'
import OperatorCopilot from './components/OperatorCopilot.jsx'
import AboutModal from './components/AboutModal.jsx'
import HighwayIntelSidebar from './components/HighwayIntelSidebar.jsx'
import { isActive } from './lib/format.js'

function readTheme() {
  try {
    return localStorage.getItem('hsa-theme') === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export default function App() {
  const { state, list, selected, now, actions } = useControlRoom()
  const [filter, setFilter] = useState('active')
  const [isAboutOpen, setIsAboutOpen] = useState(false)
  const [page, setPage] = useState('home')
  const [theme, setTheme] = useState(readTheme)
  const [corridorOverview, setCorridorOverview] = useState(null)

  const navigation = [
    ['control', 'Overview', '01'],
    ['corridor', 'Corridor', '02'],
    ['incidents', 'Incidents', '03'],
    ['activity', 'Activity', '04'],
    ['system', 'System status', '05'],
  ]

  const camera = state.camera ?? selected?.camera ?? list[0]?.camera ?? null
  const startOfDay = new Date()
  startOfDay.setHours(0, 0, 0, 0)
  const today = list.filter((i) => i.createdAt >= startOfDay.getTime()).length

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('hsa-theme', theme)
    } catch {
      // Theme still works for the current session when storage is unavailable.
    }
  }, [theme])

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.target?.matches?.('input, textarea, select, [contenteditable="true"]')) return
      if (e.key === '?' || e.key === 'a' || e.key === 'A') {
        setIsAboutOpen((prev) => !prev)
      }
      if (e.key === 'Escape' && page === 'control') setPage('home')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [page])

  return (
    <div className={`app app--${page}`}>
      {page !== 'home' && (
        <TopBar
          conn={state.conn}
          camera={camera}
          now={now}
          cameraHealth={state.cameraHealth}
          onOpenAbout={() => setIsAboutOpen(true)}
          onHome={() => setPage('home')}
          theme={theme}
          onToggleTheme={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
        />
      )}

      {page === 'home' ? (
        <Home onEnter={() => setPage('control')} conn={state.conn} incidents={list} theme={theme} onToggleTheme={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} />
      ) : (
        <>
          <nav className="ops-nav" aria-label="Operations pages">
            <div className="ops-nav-intro">
              <span className="ops-eyebrow">HIGHWAY OPERATIONS / AP</span>
              <span className="ops-nav-caption">Command interface</span>
            </div>
            <div className="ops-nav-links">
              {navigation.map(([key, label, number]) => (
                <button
                  key={key}
                  type="button"
                  className={`ops-nav-link${page === key ? ' is-current' : ''}`}
                  aria-current={page === key ? 'page' : undefined}
                  onClick={() => setPage(key)}
                >
                  <span className="ops-nav-number">{number}</span>
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </nav>

          <div className="ops-workspace-shell">
          <main className={`ops-page ops-page--${page}`}>
            <header className="ops-page-heading">
              <div>
                <span className="ops-eyebrow">FIELD INTELLIGENCE / LIVE WORKSPACE</span>
                <h1>{({
                  control: 'Operations overview',
                  corridor: 'Corridor intelligence',
                  incidents: 'Incident register',
                  activity: 'Dispatch activity',
                  system: 'System status',
                })[page] || 'Operations overview'}</h1>
                <p>{({
                  control: 'A live view of incidents, road telemetry and operator decisions.',
                  corridor: 'Explore corridor geometry and the incident locations available to the tracker.',
                  incidents: 'Review incoming events and inspect their evidence, status and response history.',
                  activity: 'Follow dispatch records and open the incident behind each action.',
                  system: 'Inspect the connection, camera health and telemetry currently reported by the application.',
                })[page]}</p>
              </div>
              <span className="ops-page-index">{navigation.findIndex(([key]) => key === page) + 1} / 05</span>
            </header>

            {page === 'control' && (
              <>
                <div className="main">
                  <section className="col">
                    <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
                      now={now} filter={filter} setFilter={setFilter} />
                  </section>
                  <section className="col col--stage">
                    <LiveStage incident={selected} camera={camera} metrics={state.metrics}
                      incidents={list} onSelectIncident={actions.select} onCorridorInfo={setCorridorOverview} />
                    <ActivityLog list={list} onSelect={actions.select} />
                  </section>
                  <section className="col">
                    <IncidentDetail incident={selected} now={now} actions={actions} />
                  </section>
                </div>
                <StatsStrip metrics={state.metrics} open={list.filter(isActive).length}
                  today={today} blackspots={state.blackspots} camera={camera} />
              </>
            )}

            {page === 'corridor' && (
              <div className="ops-single-stage">
                <LiveStage initialTab="corridor" incident={selected} camera={camera} metrics={state.metrics}
                  incidents={list} onSelectIncident={actions.select} onCorridorInfo={setCorridorOverview} />
              </div>
            )}

            {page === 'incidents' && (
              <div className="ops-two-column">
                <section className="ops-section">
                  <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
                    now={now} filter={filter} setFilter={setFilter} />
                </section>
                <section className="ops-section">
                  <IncidentDetail incident={selected} now={now} actions={actions} />
                </section>
              </div>
            )}

            {page === 'activity' && (
              <div className="ops-single-stage">
                <ActivityLog list={list} onSelect={actions.select} />
              </div>
            )}

            {page === 'system' && (
              <div className="ops-system-grid">
                <article className="ops-system-card">
                  <span className="ops-eyebrow">01 / BACKEND</span>
                  <h2>Service connection</h2>
                  <p className="ops-system-value">{String(state.conn ?? 'Unknown')}</p>
                  <p className="ops-muted">Connection state reported by the existing control-room hook.</p>
                </article>
                <article className="ops-system-card">
                  <span className="ops-eyebrow">02 / VIDEO</span>
                  <h2>Camera health</h2>
                  <p className="ops-system-value">{state.cameraHealth == null ? 'Not reported' : String(state.cameraHealth)}</p>
                  <p className="ops-muted">{camera ? `${camera.highway || 'Highway'} · ${camera.section || `KM ${camera.km ?? '—'}`}` : 'No camera selected'}</p>
                </article>
                <article className="ops-system-card">
                  <span className="ops-eyebrow">03 / TELEMETRY</span>
                  <h2>Tracker metrics</h2>
                  <p className="ops-system-value">{state.metrics?.fps == null ? 'Not reported' : `${state.metrics.fps} fps`}</p>
                  <p className="ops-muted">{state.metrics?.ruleMs == null ? 'Rule timing unavailable' : `Rule engine · ${state.metrics.ruleMs} ms`}</p>
                </article>
                <article className="ops-system-card">
                  <span className="ops-eyebrow">04 / EVENT STREAM</span>
                  <h2>Incident records</h2>
                  <p className="ops-system-value">{list.length}</p>
                  <p className="ops-muted">{list.filter(isActive).length} currently classified as active by the application.</p>
                </article>
                <div className="ops-system-metrics">
                  <StatsStrip metrics={state.metrics} open={list.filter(isActive).length}
                    today={today} blackspots={state.blackspots} camera={camera} />
                </div>
              </div>
            )}
          </main>
            <HighwayIntelSidebar
              page={page}
              onNavigate={setPage}
              incidents={list}
              activeCount={list.filter(isActive).length}
              conn={state.conn}
              metrics={state.metrics}
              camera={camera}
              corridorOverview={corridorOverview}
            />
          </div>
          <OperatorCopilot incident={selected} />
        </>
      )}

      <AboutModal isOpen={isAboutOpen} onClose={() => setIsAboutOpen(false)} />
    </div>
  )
}

function ShieldMark() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 3 34 9v10c0 9-5.7 14.5-14 18C11.7 33.5 6 28 6 19V9Z" />
      <path d="m14 20 4 4 8-9" />
    </svg>
  )
}

function ArrowIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11M10 4l6 6-6 6" /></svg>
}
