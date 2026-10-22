import { useState } from 'react'
import { Video, Map as MapIcon, Boxes } from 'lucide-react'
import LaneMap from './LaneMap.jsx'
import { isLive } from '../api/client.js'

const VIDEO_PATH = import.meta.env.VITE_VIDEO_PATH || '/video_feed'
const TWIN_URL = import.meta.env.VITE_TWIN_URL || ''

const TABS = [
  ['lane', 'Lane view', MapIcon],
  ['camera', 'Camera', Video],
  ['twin', 'Digital twin', Boxes],
]

export default function LiveStage({ incident, camera, metrics }) {
  const [tab, setTab] = useState(isLive ? 'camera' : 'lane')
  const [videoFailed, setVideoFailed] = useState(false)

  return (
    <div className="panel stage">
      <div className="panel-head">
        <div className="seg" role="tablist" aria-label="View">
          {TABS.map(([key, label, Icon]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
              <Icon size={14} aria-hidden="true" />{label}
            </button>
          ))}
        </div>
        <span className="stage-meta">{metrics ? `${metrics.fps} fps on CPU` : 'Waiting for tracker'}</span>
      </div>

      <div className="stage-body">
        {tab === 'lane' && (
          <>
            <LaneMap incident={incident} camera={camera} />
            <p className="stage-caption">Top-down view drawn from tracker telemetry. Selected incident is outlined.</p>
          </>
        )}

        {tab === 'camera' && (isLive && !videoFailed ? (
          <img className="stage-video" src={VIDEO_PATH} alt="Live camera feed with tracked vehicles" onError={() => setVideoFailed(true)} />
        ) : (
          <div className="stage-empty">
            <Video size={30} aria-hidden="true" />
            <p><b>{isLive ? 'Video stream unavailable' : 'No video in demo mode'}</b></p>
            <p>{isLive
              ? `The backend did not serve a stream at ${VIDEO_PATH}. Check VITE_VIDEO_PATH and that the tracker is running.`
              : 'Set VITE_DATA_MODE=live to show the tracker’s MJPEG feed here.'}</p>
          </div>
        ))}

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
