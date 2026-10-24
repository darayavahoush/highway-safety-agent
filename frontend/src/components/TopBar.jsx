import { Camera, Radio, BookOpen, House, Sun, Moon } from 'lucide-react'
import { fmtClock } from '../lib/format.js'
import CameraHealthBadge from './CameraHealthBadge.jsx'
import { isStale } from '../lib/freshness.js'

const PILL = {
  demo: ['Demo simulation', 'pill--amber'],
  live: ['Live connection', 'pill--green'],
  connecting: ['Connecting', 'pill--dim'],
  offline: ['Offline · retrying', 'pill--red'],
}

export default function TopBar({
  conn, camera, now, cameraHealth, cameraHealthAt, onOpenAbout,
  onHome, theme = 'dark', onToggleTheme,
}) {
  const [text, cls] = PILL[conn] || PILL.connecting

  return (
    <header className="topbar">
      <div className="brand">
        <button className="control-home-button" onClick={onHome} title="Return to homepage" aria-label="Return home">
          <House size={16} />
        </button>
        <div className="brand-crest" aria-hidden="true">
          <svg width="36" height="36" viewBox="0 0 38 38" fill="none">
            <rect width="38" height="38" rx="8" fill="#202d3b" />
            <path d="M19 7 29 12v9c0 5-4 9-10 11-6-2-10-6-10-11v-9Z" stroke="#e4ad59" strokeWidth="1.5" />
            <path d="m14 19 4 4 7-8" stroke="#79b6a0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="brand-text">
          <div className="brand-title-wrap">
            <h1>HIGHWAY SAFETY AGENT</h1>
            <span className="brand-badge">HRAP / 2026</span>
          </div>
          <p>Autonomous incident command <span className="brand-divider">/</span> Andhra Pradesh</p>
        </div>
      </div>

      {camera && (
        <div className="camera-id">
          <div className="camera-beacon"><Radio size={14} /><span className="beacon-pulse" /></div>
          <div className="camera-meta">
            <b>{camera.highway} · {camera.km ? `KM ${camera.km}` : 'CORRIDOR 42'}</b>
            <span>{camera.id}{camera.towards ? ` · Towards ${camera.towards}` : ''}</span>
          </div>
        </div>
      )}

      <div className="topbar-right">
        <CameraHealthBadge health={cameraHealth} onClick={onOpenAbout}
          staleSeconds={isStale(cameraHealthAt, now) ? Math.round((now - cameraHealthAt) / 1000) : null} />
        <button className="topbar-icon-button" onClick={onToggleTheme} title="Toggle colour theme" aria-label="Toggle colour theme">
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button className="topbar-about-btn" onClick={onOpenAbout} title="About the system">
          <BookOpen size={14} /><span>System info</span><kbd>?</kbd>
        </button>
        <span className={`pill ${cls}`}><i className="dot" />{text}</span>
        <time className="clock">{fmtClock(now)} IST</time>
      </div>
    </header>
  )
}
