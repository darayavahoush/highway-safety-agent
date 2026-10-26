import { useState, useEffect, useRef } from 'react'
import useControlRoom from './state/useControlRoom.js'
import TopBar from './components/TopBar.jsx'
import Home from './components/Home.jsx'
import IncidentQueue from './components/IncidentQueue.jsx'
import LiveStage from './components/LiveStage.jsx'
import ActivityLog from './components/ActivityLog.jsx'
import IncidentDetail from './components/IncidentDetail.jsx'
import StatsStrip from './components/StatsStrip.jsx'
import ControlRoom from './components/ControlRoom.jsx'
import CinematicPage from './components/CinematicPage.jsx'
import IncidentGuide from './components/IncidentGuide.jsx'
import SystemStatus from './components/SystemStatus.jsx'
import { PAGE_COPY } from './lib/plain.js'
import OperatorCopilot from './components/OperatorCopilot.jsx'
import AboutModal from './components/AboutModal.jsx'
import HighwayIntelSidebar from './components/HighwayIntelSidebar.jsx'
import { isActive, isBlind } from './lib/format.js'
import { resolveShortcut } from './lib/shortcuts.js'
import LiveAnnouncer from './components/LiveAnnouncer.jsx'

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
  const [page, setPage] = useState(() => {
    try {
      const p = new URLSearchParams(window.location.search).get('page')
      if (p && ['home', 'control', 'corridor', 'incidents', 'activity', 'system'].includes(p)) return p
    } catch (_) {}
    return 'home'
  })
  const [theme, setTheme] = useState(readTheme)
  const [corridorOverview, setCorridorOverview] = useState(null)

  const navigation = [
    ['control', 'Overview', '01'],
    ['corridor', 'Corridor', '02'],
    ['incidents', 'Incidents', '03'],
    ['activity', 'Activity', '04'],
    ['system', 'System status', '05'],
  ]

  const openCount = list.filter(isActive).length
  const tone = isBlind(state.conn, list) ? 'watch' : openCount === 0 ? 'clear' : list.some((i) => isActive(i) && i.severity === 'P0') ? 'critical' : 'watch'
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

  const chordAt = useRef(null)
  useEffect(() => {
    // Capture phase, so a "G then 1" jump is handled here before the Corridor tab keys see the "1".
    function handleKeyDown(e) {
      const r = resolveShortcut(e, { chordAt: chordAt.current, page, aboutOpen: isAboutOpen })
      chordAt.current = r.chord
      if (r.consume) e.stopPropagation()
      if (!r.action) return
      if (r.action.type === 'about') setIsAboutOpen(r.action.open)
      else if (r.action.type === 'page') setPage(r.action.page)
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [page, isAboutOpen])

  return (
    <div className={`app app--${page}`}>
      {page !== 'home' && <a className="skip-link" href="#main-content" onClick={(e) => { e.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to main content</a>}
      <LiveAnnouncer list={list} conn={state.conn} />
      {page !== 'home' && (
        <TopBar
          conn={state.conn}
          camera={camera}
          now={now}
          cameraHealth={state.cameraHealth}
          cameraHealthAt={state.cameraHealthAt}
          onOpenAbout={() => setIsAboutOpen(true)}
          onOpenSystem={() => setPage('system')}
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
          <main id="main-content" tabIndex={-1} className={`ops-page ops-page--${page}`}>

            {page === 'control' && (
              <ControlRoom state={state} list={list} selected={selected} now={now} actions={actions}
                filter={filter} setFilter={setFilter} camera={camera} today={today}
                onCorridorInfo={setCorridorOverview} />
            )}

            {page !== 'control' && (
              <CinematicPage now={now} tone={tone} copy={PAGE_COPY[page]}>
                {page === 'corridor' && (
                  <LiveStage initialTab="corridor" incident={selected} camera={camera} metrics={state.metrics}
                    incidents={list} onSelectIncident={actions.select} onCorridorInfo={setCorridorOverview} />
                )}

                {page === 'incidents' && (
                  <div className="cr-two">
                    <section className="cr-col">
                      <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
                        now={now} filter={filter} setFilter={setFilter} conn={state.conn} />
                    </section>
                    <section className="cr-col">
                      <IncidentGuide incident={selected} />
                      <IncidentDetail incident={selected} now={now} actions={actions} />
                    </section>
                  </div>
                )}

                {page === 'activity' && <ActivityLog list={list} onSelect={actions.select} conn={state.conn} />}

                {page === 'system' && <SystemStatus state={state} list={list} camera={camera} today={today} now={now} />}
              </CinematicPage>
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
