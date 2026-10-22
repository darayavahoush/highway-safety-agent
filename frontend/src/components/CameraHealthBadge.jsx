import React, { useState, useEffect } from 'react'
import {
  Camera,
  Sun,
  Moon,
  Sunset,
  CloudFog,
  Crosshair,
  Wind,
  Navigation,
  Info,
  CheckCircle2,
  AlertCircle
} from 'lucide-react'

export default function CameraHealthBadge({ health, onClick }) {
  const [showPopover, setShowPopover] = useState(false)

  const isStatic = health?.is_static ?? true
  const stability = health?.camera_stability || 'STATIC_LOCKED'
  const lighting = health?.lighting_condition || 'OPTIMAL_DAYLIGHT'
  const driftPx = health?.background_drift_px ?? 0.0
  const avgLum = health?.avg_luminance ?? 128.0
  const contrastRms = health?.contrast_rms ?? 52.0
  const visScore = health?.visibility_score ?? 96.0
  const motionDesc = health?.motion_status || 'Static gantry mount'

  // Stability badge styling
  let stabilityColor = '#34d399' // Green
  let StabilityIcon = Crosshair
  let stabilityLabel = 'STATIC'

  if (stability === 'WIND_SWAY') {
    stabilityColor = '#f59e0b' // Amber
    StabilityIcon = Wind
    stabilityLabel = 'SWAY'
  } else if (stability === 'PANNING_OR_DRIFT') {
    stabilityColor = '#f97316' // Orange
    StabilityIcon = Navigation
    stabilityLabel = 'DRIFT'
  }

  // Lighting badge styling
  let lightingColor = '#38bdf8' // Cyan
  let LightingIcon = Sun
  let lightingLabel = 'DAYLIGHT'

  if (lighting === 'LOW_LIGHT_DUSK') {
    lightingColor = '#fbbf24' // Amber
    LightingIcon = Sunset
    lightingLabel = 'DUSK'
  } else if (lighting === 'NIGHT_VISION') {
    lightingColor = '#818cf8' // Indigo
    LightingIcon = Moon
    lightingLabel = 'NIGHT'
  } else if (lighting === 'GLARE_OVEREXPOSURE') {
    lightingColor = '#f87171' // Red
    LightingIcon = Sun
    lightingLabel = 'GLARE'
  } else if (lighting === 'LOW_CONTRAST_FOG') {
    lightingColor = '#94a3b8' // Slate
    LightingIcon = CloudFog
    lightingLabel = 'FOG'
  }

  return (
    <div
      className="cam-health-badge-container"
      onMouseEnter={() => setShowPopover(true)}
      onMouseLeave={() => setShowPopover(false)}
    >
      <button
        className="cam-health-badge-btn"
        onClick={onClick}
        title="View Camera Diagnostics & Photometric Health"
      >
        <span className="health-chip" style={{ borderColor: `${stabilityColor}40`, color: stabilityColor }}>
          <span className="health-dot" style={{ background: stabilityColor }} />
          <StabilityIcon size={12} />
          <span>{stabilityLabel}</span>
        </span>

        <span className="health-chip" style={{ borderColor: `${lightingColor}40`, color: lightingColor }}>
          <LightingIcon size={12} />
          <span>{lightingLabel}</span>
        </span>
      </button>

      {/* Hover Diagnostics Popover */}
      {showPopover && (
        <div className="cam-health-popover">
          <div className="popover-head">
            <Camera size={14} className="text-cyan" />
            <h6>Camera Health Diagnostics</h6>
          </div>
          <div className="popover-body">
            <div className="popover-row">
              <span className="popover-label">Mount Stability:</span>
              <strong style={{ color: stabilityColor }}>{stability}</strong>
            </div>
            <div className="popover-row">
              <span className="popover-label">Background Drift:</span>
              <span>{driftPx} px / frame</span>
            </div>
            <div className="popover-desc">{motionDesc}</div>

            <div className="popover-divider" />

            <div className="popover-row">
              <span className="popover-label">Environment Light:</span>
              <strong style={{ color: lightingColor }}>{lighting}</strong>
            </div>
            <div className="popover-row">
              <span className="popover-label">Mean Luminance:</span>
              <span>{avgLum} / 255</span>
            </div>
            <div className="popover-row">
              <span className="popover-label">RMS Contrast:</span>
              <span>{contrastRms}</span>
            </div>
            <div className="popover-row">
              <span className="popover-label">Visibility Score:</span>
              <strong>{visScore}%</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
