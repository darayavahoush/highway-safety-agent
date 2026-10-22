import { useState, useEffect } from 'react'

const STAGES = [
  ['observed', 'Observed'],
  ['assessed', 'Assessed'],
  ['decided', 'Decided'],
  ['actions', 'Actions taken'],
  ['context', 'Parallel Web Intelligence'],
]

function Typed({ text, animate }) {
  const [n, setN] = useState(animate ? 0 : text.length)
  useEffect(() => {
    if (!animate) return undefined
    let i = 0
    const id = setInterval(() => {
      i += 2
      setN(i)
      if (i >= text.length) clearInterval(id)
    }, 16)
    return () => clearInterval(id)
  }, [text, animate])
  return <>{text.slice(0, n)}</>
}

function Step({ label, step }) {
  const [animate] = useState(() => (
    Date.now() - step.at < 2500 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ))
  return (
    <li className="trace-item">
      <span className="trace-dot" />
      <div>
        <b>{label}</b>
        <p><Typed text={step.text} animate={animate} /></p>
      </div>
    </li>
  )
}

export default function ReasoningTrace({ incident }) {
  const byStage = Object.fromEntries(incident.trace.map((s) => [s.stage, s]))
  const nextIdx = STAGES.findIndex(([k]) => !byStage[k])
  const working = incident.status === 'detected' || incident.status === 'analysing'

  if (incident.trace.length === 0 && !working) {
    return <p className="muted">The agent did not record reasoning for this incident.</p>
  }
  return (
    <ol className="trace">
      {STAGES.map(([key, label], i) => {
        const s = byStage[key]
        if (s) return <Step key={key} label={label} step={s} />
        if (i === nextIdx && working) {
          return (
            <li key={key} className="trace-item trace-item--pending">
              <span className="trace-dot" />
              <div>
                <b>{label}</b>
                <div className="skeleton" />
                <div className="skeleton skeleton--short" />
              </div>
            </li>
          )
        }
        return null
      })}
    </ol>
  )
}
