import { Wifi, Camera, Gauge, Timer, Database, Eye } from 'lucide-react'
import StatsStrip from './StatsStrip.jsx'
import { isActive } from '../lib/format.js'
import { cameraStatus } from '../lib/plain.js'
import { isStale } from '../lib/freshness.js'

// When updates stop arriving, say so. Old numbers must not look current.
export function withFreshness(card, at, now, what) {
  if (!isStale(at, now)) return card
  const secs = Math.round((now - at) / 1000)
  return { tone: 'warn', headline: `No update for ${secs} s`, detail: `${what} stopped reporting. Last known: ${card.headline.toLowerCase()}.` }
}

function connection(conn) {
  switch (conn) {
    case 'live': return { tone: 'ok', headline: 'Connected', detail: 'The app is receiving live data from the backend.' }
    case 'demo': return { tone: 'warn', headline: 'Running on demo data', detail: 'No live backend is attached, so incidents on screen are simulated.' }
    case 'offline': return { tone: 'bad', headline: 'Cannot reach the backend', detail: 'The app is retrying on its own. New incidents will not appear until it reconnects.' }
    default: return { tone: 'idle', headline: 'Connecting…', detail: 'Waiting for the first message from the backend.' }
  }
}

function tracker(m) {
  if (m?.fps == null) return { tone: 'idle', headline: 'Not reported yet', detail: 'The video tracker has not sent its speed.' }
  if (m.fps < 5) return { tone: 'warn', headline: `${m.fps} frames a second`, detail: 'That is slow. Fast incidents could be spotted late.' }
  return { tone: 'ok', headline: `${m.fps} frames a second`, detail: 'Fast enough to follow vehicles smoothly.' }
}

function reaction(m) {
  const s = m?.detectToDispatchS
  if (s == null) return { tone: 'idle', headline: 'Not measured yet', detail: 'This appears after the first incident is handled.' }
  return { tone: s > 10 ? 'warn' : 'ok', headline: `${s.toFixed(1)} seconds`, detail: 'Time from the camera spotting a problem to the first alert going out.' }
}

export default function SystemStatus({ state, list, camera, today, now = Date.now() }) {
  const open = list.filter(isActive).length
  const cards = [
    [Wifi, 'Connection', connection(state.conn)],
    [Camera, 'Camera', withFreshness(cameraStatus(state.cameraHealth), state.cameraHealthAt, now, 'The camera')],
    [Gauge, 'Video tracker', withFreshness(tracker(state.metrics), state.metricsAt, now, 'The video tracker')],
    [Timer, 'Speed of response', reaction(state.metrics)],
    [Database, 'Incident records', {
      tone: 'ok',
      headline: `${list.length} on file`,
      detail: `${open} still open. ${today} seen today.`,
    }],
  ]
  const count = (t) => cards.filter(([, , c]) => c.tone === t).length
  const ok = count('ok'); const warn = count('warn'); const bad = count('bad'); const idle = count('idle')
  const verdict = bad
    ? { tone: 'bad', title: 'Something is not working', text: 'Check the red card below first.' }
    : warn
      ? { tone: 'warn', title: 'Working, with things to check', text: 'Amber cards are worth a look, but nothing has stopped.' }
      : idle
        ? { tone: 'ok', title: 'Working. A few details have not been reported yet', text: 'Grey cards simply have not sent anything yet.' }
        : { tone: 'ok', title: 'Everything is working', text: 'Every part of the system reported in and looks healthy.' }
  return (
    <>
      <div className="cr-verdict" data-tone={verdict.tone} role="status">
        <i aria-hidden="true" />
        <div><b>{verdict.title}</b><span>{verdict.text}</span></div>
        <ul aria-label="Summary">
          <li><b>{ok}</b> working</li>
          {warn > 0 && <li><b>{warn}</b> to check</li>}
          {bad > 0 && <li><b>{bad}</b> failing</li>}
          {idle > 0 && <li><b>{idle}</b> not reported</li>}
        </ul>
      </div>
      <div className="cr-health">
        {cards.map(([Icon, label, c]) => (
          <article key={label} className="cr-health-card" data-tone={c.tone}>
            <span className="cr-health-label"><Icon size={15} aria-hidden="true" />{label}</span>
            <b><i aria-hidden="true" />{c.headline}</b>
            <p>{c.detail}</p>
          </article>
        ))}
      </div>
      <details className="cr-tech">
        <summary><Eye size={14} aria-hidden="true" />Technical performance <span>for engineers</span></summary>
        <StatsStrip metrics={state.metrics} open={open} today={today} blackspots={state.blackspots} camera={camera} />
      </details>
    </>
  )
}
