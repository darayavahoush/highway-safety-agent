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
      {page === 'home' ? (
        <header className="landing-nav">
          <button className="landing-wordmark" onClick={() => setPage('home')} aria-label="Highway Safety Agent home">
            <span className="landing-mark"><ShieldMark /></span>
            <span><strong>HIGHWAY SAFETY</strong><small>INTELLIGENCE PLATFORM</small></span>
          </button>
          <div className="landing-nav-right">
            <span className="landing-nav-label">HRAP / 2026</span>
            <button className="theme-toggle" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} title="Toggle colour theme">
              {theme === 'dark' ? 'LIGHT ↗' : 'DARK ↗'}
            </button>
            <button className="landing-nav-enter" onClick={() => setPage('control')}>
              Control room <ArrowIcon />
            </button>
          </div>
        </header>
      ) : (
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
        <Home onEnter={() => setPage('control')} conn={state.conn} incidents={list} />
      ) : (
        <>
          <main className="main">
            <section className="col">
              <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
                now={now} filter={filter} setFilter={setFilter} />
            </section>
            <section className="col col--stage">
              <LiveStage incident={selected} camera={camera} metrics={state.metrics}
                incidents={list} onSelectIncident={actions.select} />
              <ActivityLog list={list} onSelect={actions.select} />
            </section>
            <section className="col">
              <IncidentDetail incident={selected} now={now} actions={actions} />
            </section>
          </main>
          <StatsStrip metrics={state.metrics} open={list.filter(isActive).length}
            today={today} blackspots={state.blackspots} camera={camera} />
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
