import { useState, useEffect } from 'react'
import useControlRoom from './state/useControlRoom.js'
import TopBar from './components/TopBar.jsx'
import IncidentQueue from './components/IncidentQueue.jsx'
import LiveStage from './components/LiveStage.jsx'
import ActivityLog from './components/ActivityLog.jsx'
import IncidentDetail from './components/IncidentDetail.jsx'
import StatsStrip from './components/StatsStrip.jsx'
import OperatorCopilot from './components/OperatorCopilot.jsx'
import AboutModal from './components/AboutModal.jsx'
import { isActive } from './lib/format.js'

export default function App() {
  const { state, list, selected, now, actions } = useControlRoom()
  const [filter, setFilter] = useState('active')
  const [isAboutOpen, setIsAboutOpen] = useState(false)
  const camera = state.camera ?? selected?.camera ?? list[0]?.camera ?? null
  const startOfDay = new Date(); startOfDay.setHours(0, 0, 0, 0)
  const today = list.filter((i) => i.createdAt >= startOfDay.getTime()).length

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      if (e.key === '?' || e.key === 'a' || e.key === 'A') {
        setIsAboutOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="app">
      <TopBar
        conn={state.conn}
        camera={camera}
        now={now}
        cameraHealth={state.cameraHealth}
        onOpenAbout={() => setIsAboutOpen(true)}
      />
      <main className="main">
        <section className="col">
          <IncidentQueue list={list} selectedId={state.selectedId} onSelect={actions.select}
                         now={now} filter={filter} setFilter={setFilter} />
        </section>
        <section className="col col--stage">
          <LiveStage
            incident={selected}
            camera={camera}
            metrics={state.metrics}
            incidents={list}
            onSelectIncident={actions.select}
          />
          <ActivityLog list={list} onSelect={actions.select} />
        </section>
        <section className="col">
          <IncidentDetail incident={selected} now={now} actions={actions} />
        </section>
      </main>
      <StatsStrip metrics={state.metrics} open={list.filter(isActive).length} today={today}
                  blackspots={state.blackspots} camera={camera} />
      <OperatorCopilot incident={selected} />
      <AboutModal isOpen={isAboutOpen} onClose={() => setIsAboutOpen(false)} />
    </div>
  )
}
