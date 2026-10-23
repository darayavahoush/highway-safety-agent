import { Camera, ShieldAlert, Radio, BookOpen } from 'lucide-react'
import { fmtClock } from '../lib/format.js'
import CameraHealthBadge from './CameraHealthBadge.jsx'

const PILL = {
  demo: ['Demo Simulation', 'pill--amber'],
  live: ['AP Gov Live Sentry', 'pill--green'],
  connecting: ['Connecting to Gantry', 'pill--dim'],
  offline: ['Sentry Offline, Retrying', 'pill--red'],
}

export default function TopBar({ conn, camera, now, cameraHealth, onOpenAbout }) {
  const [text, cls] = PILL[conn] || PILL.connecting
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-crest">
          <svg width="38" height="38" viewBox="0 0 38 38" fill="none" aria-hidden="true">
            <rect width="38" height="38" rx="9" fill="url(#crestGrad)" />
            <path d="M19 8L28 13V21C28 26 24 30 19 31C14 30 10 26 10 21V13L19 8Z" stroke="#F4B63F" strokeWidth="2" strokeLinejoin="round" fill="rgba(0,0,0,0.3)" />
            <path d="M15 19L18 22L24 16" stroke="#2DB67D" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            <defs>
              <linearGradient id="crestGrad" x1="0" y1="0" x2="38" y2="38" gradientUnits="userSpaceOnUse">
                <stop stopColor="#1E3A8A" />
                <stop offset="1" stopColor="#0B192C" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div className="brand-text">
          <div className="brand-title-wrap">
            <h1>HIGHWAY ROAD ACCIDENT PREVENTION</h1>
            <span className="brand-badge">HRAP-2026</span>
          </div>
          <p>
            <span className="gov-tag">Govt of Andhra Pradesh</span> · <span className="rtih-tag">Ratan Tata Innovation Hub</span> · Autonomous Incident Command
          </p>
        </div>
      </div>

      {camera && (
        <div className="camera-id">
          <div className="camera-beacon">
            <Radio size={14} className="radar-icon" aria-hidden="true" />
            <span className="beacon-pulse" />
          </div>
          <div className="camera-meta">
            <b>{camera.highway} · {camera.km ? `KM ${camera.km}` : 'CORRIDOR 42'}</b>
            <span>{camera.id} {camera.towards ? `(towards ${camera.towards})` : ''}</span>
          </div>
        </div>
      )}

      <div className="topbar-right">
        {/* Real-time Camera Stability & Photometric Lighting Diagnostics */}
        <CameraHealthBadge health={cameraHealth} onClick={onOpenAbout} />

        {/* Informative About System & Architecture Docs */}
        <button
          className="topbar-about-btn"
          onClick={onOpenAbout}
          title="About Highway Safety Agent & HRAP-2026 Documentation (? / A)"
        >
          <BookOpen size={13} />
          <span>About System</span>
          <kbd className="about-kbd-hint">?</kbd>
        </button>

        <span className={`pill ${cls}`}>
          <i className="dot" />
          {text}
        </span>
        <time className="clock">{fmtClock(now)} IST</time>
      </div>
    </header>
  )
}
