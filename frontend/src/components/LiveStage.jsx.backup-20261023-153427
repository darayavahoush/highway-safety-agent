import { useState, useEffect } from 'react'
import { Video, Map as MapIcon, Boxes, Compass, Film } from 'lucide-react'
import LaneMap from './LaneMap.jsx'
import CorridorMap3D from './CorridorMap3D.jsx'
import { isLive } from '../api/client.js'

const VIDEO_PATH = import.meta.env.VITE_VIDEO_PATH || '/video_feed'
const TWIN_URL = import.meta.env.VITE_TWIN_URL || ''

const TABS = [
  ['camera', 'Camera', Video],
  ['corridor', '3D Corridor Map', Compass],
  ['lane', 'Lane view', MapIcon],
  ['twin', 'Digital twin', Boxes],
]

export default function LiveStage({ incident, camera, metrics, incidents = [], onSelectIncident }) {
  const [tab, setTab] = useState(isLive ? 'camera' : 'corridor')
  const [videoFailed, setVideoFailed] = useState(false)
  const [clips, setClips] = useState([])
  const [activeClip, setActiveClip] = useState('')
  const [switchingClip, setSwitchingClip] = useState(false)

  // Fetch available real highway sample clips (including HuggingFace drone clips)
  useEffect(() => {
    if (!isLive) return
    fetch('/api/clips')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.clips) {
          setClips(data.clips)
          setActiveClip(data.active_clip || '')
        }
      })
      .catch(() => {})
  }, [])

  const handleClipChange = async (clipId) => {
    setSwitchingClip(true)
    try {
      const res = await fetch('/api/clips/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clip_id: clipId }),
      })
      if (res.ok) {
        const data = await res.json()
        setActiveClip(data.active_clip)
        setVideoFailed(false)
      }
    } catch (e) {
      console.error('Failed to switch clip:', e)
    } finally {
      setSwitchingClip(false)
    }
  }

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      if (e.key === '1') setTab('camera')
      if (e.key === '2') setTab('corridor')
      if (e.key === '3') setTab('lane')
      if (e.key === '4') setTab('twin')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="panel stage">
      <div className="panel-head">
        <div className="seg" role="tablist" aria-label="View">
          {TABS.map(([key, label, Icon], idx) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              title={`Switch to ${label} [${idx + 1}]`}
            >
              <Icon size={14} aria-hidden="true" />
              <span>{label}</span>
              <kbd className="tab-kbd-hint">{idx + 1}</kbd>
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {tab === 'camera' && clips.length > 0 && (
            <div className="clip-selector-group" title="Select real highway sample clip (HF Drone & CCTV)">
              <Film size={12} style={{ color: 'var(--dim)' }} />
              <select
                className="clip-select"
                value={activeClip}
                disabled={switchingClip}
                onChange={(e) => {
                  const selected = clips.find((c) => c.path.endsWith(e.target.value))
                  if (selected) handleClipChange(selected.id)
                }}
              >
                {clips.map((c) => (
                  <option key={c.id} value={c.path.split('/').pop()}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <span className="stage-meta">{metrics ? `${metrics.fps} fps on CPU` : 'Waiting for tracker'}</span>
        </div>
      </div>

      <div className="stage-body">
        {tab === 'camera' && (isLive && !videoFailed ? (
          <img
            className="stage-video"
            src={`${VIDEO_PATH}?t=${activeClip}`}
            alt="Live camera feed with tracked vehicles"
            onError={() => setVideoFailed(true)}
          />
        ) : (
          <div className="stage-empty">
            <Video size={30} aria-hidden="true" />
            <p><b>{isLive ? 'Video stream unavailable' : 'No video in demo mode'}</b></p>
            <p>{isLive
              ? `The backend did not serve a stream at ${VIDEO_PATH}. Check VITE_VIDEO_PATH and that the tracker is running.`
              : 'Set VITE_DATA_MODE=live to show the tracker’s MJPEG feed here.'}</p>
          </div>
        ))}

        {tab === 'corridor' && (
          <CorridorMap3D
            incidents={incidents}
            selectedIncident={incident}
            onSelectIncident={onSelectIncident}
            camera={camera}
          />
        )}

        {tab === 'lane' && (
          <>
            <LaneMap incident={incident} camera={camera} />
            <p className="stage-caption">Top-down view drawn from tracker telemetry. Selected incident is outlined.</p>
          </>
        )}

        {tab === 'twin' && (TWIN_URL ? (
          <iframe className="stage-video" src={TWIN_URL} title="3D digital twin" />
        ) : (
          <div className="stage-empty">
            <Boxes size={30} aria-hidden="true" />
            <p><b>Digital twin not connected</b></p>
            <p>Set VITE_TWIN_URL to the page that serves the Three.js twin and it will load here.</p>
          </div>
        ))}
      </div>
    </div>
  )
}
