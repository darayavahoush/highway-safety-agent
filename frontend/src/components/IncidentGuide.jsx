import { Lightbulb } from 'lucide-react'
import { SEVERITY } from '../lib/format.js'
import { whyItMatters, nextStep } from '../lib/plain.js'

export default function IncidentGuide({ incident }) {
  if (!incident) return null
  return (
    <div className="cr-guide" style={{ '--sev': (SEVERITY[incident.severity] || SEVERITY.P1).color }}>
      <Lightbulb size={16} aria-hidden="true" />
      <div>
        <p><b>Why it matters.</b> {whyItMatters(incident.type)}</p>
        <p><b>Your next step.</b> {nextStep(incident)}</p>
      </div>
    </div>
  )
}
