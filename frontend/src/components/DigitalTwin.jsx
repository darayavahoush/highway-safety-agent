import { useMemo } from 'react'
import { Boxes, Camera, CarFront, MapPin, Radio } from 'lucide-react'

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

function getIncidentId(item) {
  return item?.id ?? item?.incidentId ?? item?.trackId ?? null
}

function getSeverity(item) {
  const value = String(item?.severity ?? item?.priority ?? '').toUpperCase()
  if (value === 'P0' || value === 'CRITICAL') return 'critical'
  if (value === 'P1' || value === 'HIGH') return 'high'
  return 'normal'
}

export default function DigitalTwin({
  incidents = [],
  incident = null,
  camera = null,
  onSelectIncident,
}) {
  const sceneItems = useMemo(() => {
    return incidents.slice(0, 12).map((item, index) => {
      // These positions are illustrative scene positions, not GPS coordinates.
      const lane = index % 3
      const progress = (index * 17 + 18) % 76
      return {
        item,
        id: getIncidentId(item) ?? `scene-${index}`,
        lane,
        x: 390 + (progress * 4.8),
        y: 300 - progress * 2.25 + lane * 19,
        severity: getSeverity(item),
      }
    })
  }, [incidents])

  const selectedId = getIncidentId(incident)
  const cameraName = camera?.id ?? camera?.name ?? 'Highway camera'
  const activeCount = incidents.length

  return (
    <section className="twin-scene" aria-label="Interactive highway digital twin">
      <header className="twin-toolbar">
        <div className="twin-heading">
          <span className="twin-heading-icon"><Boxes size={18} /></span>
          <div>
            <h2>Highway digital twin</h2>
            <p>Perspective scene · illustrative positions</p>
          </div>
        </div>
        <div className="twin-status"><i /> LOCAL SIMULATION</div>
      </header>

      <div className="twin-canvas">
        <div className="twin-sky-glow" />
        <div className="twin-horizon" />
        <svg
          className="twin-road-svg"
          viewBox="0 0 1000 620"
          role="img"
          aria-label="Perspective highway with lane markings, roadside cameras and selectable incident markers"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <linearGradient id="twinRoad" x1="0" y1="0" x2="0.2" y2="1">
              <stop offset="0%" stopColor="#202e3e" />
              <stop offset="100%" stopColor="#080e17" />
            </linearGradient>
            <linearGradient id="twinShoulder" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#172b39" />
              <stop offset="100%" stopColor="#0c1722" />
            </linearGradient>
            <pattern id="twinGrid" width="36" height="36" patternUnits="userSpaceOnUse">
              <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#274054" strokeWidth="0.7" opacity=".35" />
            </pattern>
          </defs>

          <rect width="1000" height="620" fill="url(#twinGrid)" />
          <path d="M0 210 L1000 210 L1000 620 L0 620Z" fill="#0b131d" opacity=".35" />
          <path d="M350 200 L650 200 L1000 620 L0 620Z" fill="url(#twinShoulder)" />
          <path d="M390 200 L610 200 L895 620 L105 620Z" fill="url(#twinRoad)" stroke="#52687c" strokeWidth="2" />

          <path d="M390 200 L105 620" stroke="#d9e4ee" strokeWidth="3" opacity=".65" />
          <path d="M610 200 L895 620" stroke="#d9e4ee" strokeWidth="3" opacity=".65" />

          {[0.25, 0.5, 0.75].map((fraction) => {
            const topX = 390 + 220 * fraction
            const bottomX = 105 + 790 * fraction
            return (
              <path
                key={fraction}
                d={`M${topX} 200 L${bottomX} 620`}
                stroke="#91a5b9"
                strokeWidth="2"
                strokeDasharray="22 18"
                opacity=".72"
              />
            )
          })}

          {[0, 1, 2, 3, 4, 5, 6].map((index) => {
            const y = 230 + index * index * 7.5
            const halfWidth = 110 + (y - 200) * 0.68
            return (
              <path
                key={index}
                d={`M${500 - halfWidth} ${y} L${500 + halfWidth} ${y}`}
                stroke="#284052"
                strokeWidth="1"
                opacity=".5"
              />
            )
          })}

          <g className="twin-road-label">
            <rect x="425" y="230" width="150" height="34" rx="8" />
            <text x="500" y="251" textAnchor="middle">NH-16 · SIMULATED</text>
          </g>

          {/* Roadside equipment is part of the illustration, not surveyed assets. */}
          <g transform="translate(325 335)">
            <path d="M0 0 L0 85" stroke="#71869b" strokeWidth="5" />
            <path d="M-3 0 L45 -14" stroke="#71869b" strokeWidth="5" />
            <rect x="32" y="-24" width="27" height="17" rx="3" fill="#263c4e" stroke="#7dd3fc" />
            <circle cx="45" cy="-15" r="4" fill="#7dd3fc" />
          </g>
          <g transform="translate(710 365)">
            <path d="M0 0 L0 80" stroke="#71869b" strokeWidth="5" />
            <path d="M0 0 L-40 -13" stroke="#71869b" strokeWidth="5" />
            <rect x="-65" y="-23" width="27" height="17" rx="3" fill="#263c4e" stroke="#7dd3fc" />
            <circle cx="-52" cy="-14" r="4" fill="#7dd3fc" />
          </g>

          {sceneItems.map(({ item, id, lane, x, y, severity }) => {
            const isSelected = selectedId != null && String(selectedId) === String(id)
            const color = severity === 'critical' ? '#fb5252' : severity === 'high' ? '#fbbf24' : '#38bdf8'
            const scale = clamp(0.45 + (y / 620) * 0.7, 0.5, 1.15)
            return (
              <g
                key={id}
                className={`twin-vehicle ${isSelected ? 'is-selected' : ''}`}
                transform={`translate(${x + lane * 7} ${y}) scale(${scale})`}
                role="button"
                tabIndex="0"
                aria-label={`Select incident ${item?.type ?? item?.title ?? id}`}
                onClick={() => onSelectIncident?.(item)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelectIncident?.(item)
                  }
                }}
                style={{ cursor: onSelectIncident ? 'pointer' : 'default' }}
              >
                {isSelected && <circle r="27" fill={color} opacity=".12" />}
                <circle r={isSelected ? 20 : 16} fill={color} opacity=".17" />
                <rect x="-12" y="-19" width="24" height="38" rx="6" fill="#111e2c" stroke={color} strokeWidth={isSelected ? 3 : 1.5} />
                <rect x="-7" y="-13" width="14" height="12" rx="3" fill={color} opacity=".85" />
                <rect x="-7" y="5" width="14" height="8" rx="2" fill="#8195a8" opacity=".8" />
                <circle cx="-13" cy="-11" r="2.5" fill="#dce7f0" />
                <circle cx="13" cy="-11" r="2.5" fill="#dce7f0" />
                <circle cx="-13" cy="12" r="2.5" fill="#dce7f0" />
                <circle cx="13" cy="12" r="2.5" fill="#dce7f0" />
                {isSelected && (
                  <g className="twin-selected-label">
                    <rect x="-65" y="-47" width="130" height="21" rx="5" />
                    <text x="0" y="-33" textAnchor="middle">
                      {String(item?.type ?? item?.title ?? 'Selected incident').replace(/_/g, ' ').slice(0, 22)}
                    </text>
                  </g>
                )}
              </g>
            )
          })}
        </svg>

        <div className="twin-canvas-label twin-canvas-label--top">
          <span><Radio size={13} /> {cameraName}</span>
          <span>{activeCount} tracked incident{activeCount === 1 ? '' : 's'}</span>
        </div>
        <div className="twin-canvas-label twin-canvas-label--bottom">
          <span><Camera size={13} /> Camera positions illustrative</span>
          <span><MapPin size={13} /> Not GPS-accurate</span>
        </div>
        {activeCount === 0 && (
          <div className="twin-no-incidents">
            <CarFront size={20} />
            <span>No incidents in the current feed</span>
          </div>
        )}
      </div>

      <footer className="twin-footer">
        <div className="twin-legend">
          <span><i className="critical" /> Critical</span>
          <span><i className="high" /> High</span>
          <span><i className="normal" /> Other</span>
        </div>
        <p>Select a vehicle to inspect its incident in the control room.</p>
      </footer>
    </section>
  )
}
