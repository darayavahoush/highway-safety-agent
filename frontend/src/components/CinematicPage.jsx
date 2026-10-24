import { sceneFor } from '../lib/plain.js'

// Shared shell for every page after the homepage: time-of-day photograph,
// vignette and grain behind everything, plus an optional plain-language heading.
export default function CinematicPage({ now, tone = 'clear', copy, children }) {
  return (
    <div className="cr-wrap" data-scene={sceneFor(now)} data-tone={tone}>
      <div className="cr-backdrop" aria-hidden="true" />
      <div className="cr">
        {copy && (
          <header className="cr-pagehead">
            <span className="cr-kicker">{copy.kicker}</span>
            <h2>{copy.title}</h2>
            <p>{copy.lead}</p>
          </header>
        )}
        {children}
      </div>
    </div>
  )
}
