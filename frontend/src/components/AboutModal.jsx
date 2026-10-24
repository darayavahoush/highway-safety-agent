import React, { useEffect, useRef } from 'react'
import {
  X,
  Shield,
  Cpu,
  Eye,
  Camera,
  Activity,
  Zap,
  MapPin,
  Clock,
  Sparkles,
  Award,
  BookOpen,
  Keyboard,
  CheckCircle2,
  AlertTriangle,
  Building2,
  Hospital
} from 'lucide-react'

// Controls hidden inside a closed <details> (other than its own <summary>) cannot take focus.
const canFocus = (el) => {
  if (el.hidden || el.closest('[hidden]')) return false
  const d = el.closest('details:not([open])')
  return !d || (el.tagName === 'SUMMARY' && el.parentElement === d)
}
const FOCUSABLE = 'a[href], button:not([disabled]), summary, input, select, textarea, [tabindex]:not([tabindex="-1"])'

export default function AboutModal({ isOpen, onClose }) {
  const box = useRef(null)
  const opener = useRef(null)

  useEffect(() => {
    if (!isOpen) return undefined
    opener.current = document.activeElement
    // Move focus into the dialog, and keep Tab inside it while it is open.
    const first = box.current?.querySelector('.about-close-btn') || box.current
    first?.focus()
    function onKey(e) {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab' || !box.current) return
      const items = [...box.current.querySelectorAll(FOCUSABLE)].filter(canFocus)
      if (items.length === 0) { e.preventDefault(); return }
      const a = items[0]; const z = items[items.length - 1]
      if (e.shiftKey && (document.activeElement === a || !box.current.contains(document.activeElement))) { e.preventDefault(); z.focus() }
      else if (!e.shiftKey && (document.activeElement === z || !box.current.contains(document.activeElement))) { e.preventDefault(); a.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      // Give focus back to whatever opened the dialog.
      if (opener.current?.isConnected) opener.current.focus?.()
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="about-modal" ref={box} role="dialog" aria-modal="true" aria-labelledby="about-title" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="about-modal-head">
          <div className="about-modal-title">
            <div className="about-shield-icon">
              <Shield size={24} className="text-cyan" />
            </div>
            <div>
              <h3 id="about-title">About Highway Safety Agent</h3>
              <p className="about-modal-sub">A road-accident prevention tool for Andhra Pradesh highways (HRAP-2026)</p>
            </div>
          </div>
          <button className="about-close-btn" onClick={onClose} title="Close (Esc)" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div className="about-modal-body">
          <section className="about-plain">
            <h4>What this does, in 10 seconds</h4>
            <div className="about-steps">
              <div><b>1</b><strong>A camera watches the road</strong><p>The system spots stopped vehicles, wrong-way driving, cars too close together and crashes, within seconds.</p></div>
              <div><b>2</b><strong>The agent tells the right people</strong><p>It alerts patrols, ambulances, police and roadside signs, and writes a short briefing for you.</p></div>
              <div><b>3</b><strong>You make the call</strong><p>Open an incident to see why it matters and what to do next. Mark it real, or a false alarm.</p></div>
            </div>
            <ul className="about-key">
              <li><i style={{ background: '#ef4444' }} /><b>Critical</b> Act now</li>
              <li><i style={{ background: '#f5b942' }} /><b>High</b> Check soon</li>
              <li><i style={{ background: '#5cb8ff' }} /><b>Watch</b> Keep an eye on it</li>
            </ul>
            <p className="about-demo">“Demo simulation” means you are looking at sample data. No real emergency is happening. Press <kbd>?</kbd> any time to open this help, or <kbd>G</kbd> then <kbd>1</kbd> to <kbd>5</kbd> to jump between pages.</p>
          </section>
          <details className="about-tech">
            <summary>Technical details and keyboard shortcuts <span>for engineers</span></summary>
          {/* Mission Banner */}
          <div className="about-banner">
            <div className="about-banner-badge">
              <Award size={14} />
              <span>HRAP-2026 Flagship Innovation</span>
            </div>
            <h4>Autonomous Edge Perception & Cognitive Incident Command for High-Speed Corridors</h4>
            <p>
              An edge-first highway intelligence system deployed on low-cost compute (Raspberry Pi 4/5 & edge SBCs) to eliminate the
              fatal response gap along the <strong>NH-16 (Chennai–Kolkata)</strong> and <strong>NH-44 (Rayalaseema)</strong> corridors.
              It operates on a strict <strong>Two-Tier Architecture</strong> that marries deterministic, zero-latency edge physics with
              on-demand cognitive AI debriefing.
            </p>
          </div>

          {/* Core Pillars */}
          <div className="about-grid">
            {/* Pillar 1: Deterministic Safety Floor */}
            <div className="about-card">
              <div className="about-card-icon about-card-icon--cyan">
                <Cpu size={20} />
              </div>
              <h5>Tier 0: Sub-3ms Deterministic Safety Floor</h5>
              <p className="about-card-desc">
                Runs 100% locally in pure Python/NumPy on CPU. Zero LLM calls in the perception loop ensures deterministic 15–30 FPS
                throughput with zero cloud latency and zero API credit burn:
              </p>
              <ul className="about-card-list">
                <li><strong>ByteTrack & 8-State Kalman Filter:</strong> Replaces centroid tracking with two-stage IoU association, eliminating ID switches on vehicle crossovers.</li>
                <li><strong>Kinematic Smoothing & Spike Isolation:</strong> 0.5s sliding window speed calculation with hard physical spike rejection (&gt;200 km/h) rejecting tracking jumps.</li>
                <li><strong>Multi-Lane Flow Vectors:</strong> Evaluates opposing angle (&gt;135°) and displacement (&ge;5m) to catch genuine wrong-way drivers.</li>
                <li><strong>Congestion Suppression:</strong> Automatically suppresses false stalled alerts when surrounding lane median speed is &lt;15 km/h.</li>
                <li><strong>Feeder-Road Merge Intrusion (P1):</strong> Flags reckless slip-road vehicles cutting across boundary into live travel lanes with lateral velocity &gt;8 km/h.</li>
                <li><strong>Dusk/Night Stationary Protocol:</strong> Elevates unlit shoulder stops from P2 monitoring to P1 emergency hazard after dusk.</li>
              </ul>
            </div>

            {/* Pillar 2: Cognitive Agent & On-Demand Copilot */}
            <div className="about-card">
              <div className="about-card-icon about-card-icon--green">
                <Sparkles size={20} />
              </div>
              <h5>Tier 1: Cognitive Safety Agent & AI Copilot</h5>
              <p className="about-card-desc">
                High-level cognitive synthesis powered by <strong>Parallel AI Web Intelligence</strong>, invoked strictly on-demand when operators request debriefing:
              </p>
              <ul className="about-card-list">
                <li><strong>4-Stage Audit Trail:</strong> Every incident synthesizes an unalterable forensic trace: <em>Observed &rarr; Assessed &rarr; Decided &rarr; Actions</em>.</li>
                <li><strong>15-Second Human-in-the-Loop Window:</strong> Automated dispatches enter a 15s queued cancellation countdown before outward transmission.</li>
                <li><strong>On-Demand "Explain with AI":</strong> Operators click for real-time debriefing grounded in MoRTH safety guidelines and live trauma routing.</li>
                <li><strong>Operator Copilot Drawer:</strong> Interactive conversational assistant with prompt chips for bilingual Telugu VMS alerts and corridor blackspot risks.</li>
                <li><strong>Strict Credit Preservation:</strong> Zero automated background calls; 100% of background perception is deterministic and cost-free.</li>
              </ul>
            </div>

            {/* Pillar 3: Edge ANPR */}
            <div className="about-card">
              <div className="about-card-icon about-card-icon--purple">
                <Eye size={20} />
              </div>
              <h5>Edge ANPR & Temporal Voting</h5>
              <p className="about-card-desc">
                Automated license plate recognition designed specifically for Indian High Security Registration Plates (HSRP):
              </p>
              <ul className="about-card-list">
                <li><strong>Bumper Localization:</strong> Slices the bottom 45% bumper zone with Sobel rectangular morphological gating (aspect 2.0–5.5).</li>
                <li><strong>HSRP Normalization:</strong> Regex engine standardizing state prefix, district RTO, series, and 4-digit registration (e.g. <code>AP 16 TX 4921</code>).</li>
                <li><strong>Temporal Consensus Voting:</strong> Aggregates plate reads across multi-frame tracking history to eliminate single-frame OCR jitter.</li>
                <li><strong>Hotlist Cross-Referencing:</strong> Alerts operators instantly for wanted hit-and-run vehicles, stolen freight, and repeat speed offenders.</li>
              </ul>
            </div>

            {/* Pillar 4: Camera Health & Photometrics */}
            <div className="about-card">
              <div className="about-card-icon about-card-icon--amber">
                <Camera size={20} />
              </div>
              <h5>Camera Stability & Photometric Telemetry</h5>
              <p className="about-card-desc">
                Real-time edge diagnostics evaluating physical mounting health and environmental viewing conditions:
              </p>
              <ul className="about-card-list">
                <li><strong>Static vs Moving Classifier:</strong> Sparse background optical flow distinguishes <em>Static Locked</em> poles from <em>Wind Sway / Vibration</em> and <em>Drone Drift</em>.</li>
                <li><strong>Photometric Lighting Analyzer:</strong> Calculates mean luminance and RMS contrast to categorize Daylight, Dusk, Night Vision, Glare, or Fog.</li>
                <li><strong>Dynamic Night Protocol:</strong> Automatically engages unlit obstacle safety rules when luminance falls below 75 units, even without clock sync.</li>
                <li><strong>Visibility Scoring:</strong> Computes real-time 0–100% atmospheric visibility index for automated highway advisory gantries.</li>
              </ul>
            </div>
          </div>

          {/* AP Corridor & Trauma Network */}
          <div className="about-section">
            <div className="about-section-head">
              <MapPin size={18} className="text-cyan" />
              <h4>Andhra Pradesh Corridor & Golden-Hour Trauma Care Network</h4>
            </div>
            <div className="about-corridor-grid">
              <div className="about-corridor-card">
                <h6>MoRTH / AP Police Blackspot Data</h6>
                <div className="corridor-stat-row">
                  <span>NTR / Vijayawada District</span>
                  <strong>197 blackspots</strong>
                </div>
                <div className="corridor-stat-row">
                  <span>Guntur Capital Region</span>
                  <strong>58 blackspots</strong>
                </div>
                <div className="corridor-stat-row">
                  <span>Visakhapatnam Corridor</span>
                  <strong>131 blackspots</strong>
                </div>
                <div className="corridor-stat-row">
                  <span>NH-44 Anantapur Stretch</span>
                  <strong>87 blackspots</strong>
                </div>
              </div>

              <div className="about-corridor-card">
                <h6>Designated Level-1 Trauma Care Network</h6>
                <div className="hospital-row">
                  <Hospital size={14} className="text-green" />
                  <div>
                    <strong>AIIMS Mangalagiri</strong>
                    <p>Apex Level-1 Trauma Centre (Target transit &lt; 10 mins · Ph: 08645-280021)</p>
                  </div>
                </div>
                <div className="hospital-row">
                  <Hospital size={14} className="text-cyan" />
                  <div>
                    <strong>GGH Guntur</strong>
                    <p>Tertiary Trauma Care Centre (108 Emergency Ambulance network)</p>
                  </div>
                </div>
                <div className="hospital-row">
                  <Hospital size={14} className="text-cyan" />
                  <div>
                    <strong>GGH Vijayawada (SMC)</strong>
                    <p>Acute Emergency Trauma Campus (Hanumanpet / Siddhartha Medical)</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Keyboard Shortcuts & Accessibility */}
          <div className="about-section">
            <div className="about-section-head">
              <Keyboard size={18} className="text-cyan" />
              <h4>Keyboard shortcuts</h4>
            </div>
            <div className="shortcuts-grid">
              <div className="shortcut-item">
                <kbd>G</kbd> then <kbd>1</kbd> to <kbd>5</kbd>
                <span>Go to Overview, Corridor, Incidents, Activity or System status</span>
              </div>
              <div className="shortcut-item">
                <kbd>1</kbd> to <kbd>4</kbd>
                <span>On the Corridor page: Live camera, Road map, Lanes, Simulation</span>
              </div>
              <div className="shortcut-item">
                <kbd>H</kbd>
                <span>Back to the home page</span>
              </div>
              <div className="shortcut-item">
                <kbd>?</kbd> or <kbd>A</kbd>
                <span>Open or close this help window</span>
              </div>
              <div className="shortcut-item">
                <kbd>Esc</kbd>
                <span>Close this window, or leave the control room</span>
              </div>
            </div>
          </div>
          </details>
        </div>

        {/* Footer */}
        <div className="about-modal-foot">
          <span className="about-version">Highway Safety Agent v2.4.0 · AP-HRAP Build · MIT Licensed</span>
          <button className="btn btn--primary" onClick={onClose}>
            Return to Control Room
          </button>
        </div>
      </div>
    </div>
  )
}
