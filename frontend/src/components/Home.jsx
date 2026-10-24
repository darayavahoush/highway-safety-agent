import {
  ArrowDownRight, ArrowRight, Activity, ShieldCheck, Radio,
  MapPinned, ScanEye, Command, ChevronRight, MoveUpRight,
  Zap, Radar, Orbit, Sun, Moon
} from 'lucide-react'

const capabilities = [
  {
    number: '01',
    icon: ScanEye,
    tag: 'SEE THE UNSEEN',
    title: 'Incident intelligence',
    text: 'Bring emerging incidents into focus. Review events, understand their severity and decide what deserves attention first.',
    accent: 'lime',
  },
  {
    number: '02',
    icon: MapPinned,
    tag: 'THINK IN CORRIDORS',
    title: 'Corridor awareness',
    text: 'Move from an individual incident to the wider road environment with corridor views and a digital-twin experience.',
    accent: 'violet',
  },
  {
    number: '03',
    icon: Command,
    tag: 'TURN INSIGHT INTO ACTION',
    title: 'Coordinated response',
    text: 'Keep incident context, operational decisions and response planning connected in one workspace.',
    accent: 'pink',
  },
]

export default function Home({ onEnter, conn, incidents = [], theme = 'dark', onToggleTheme }) {
  const connectionLabel = conn === 'live'
    ? 'LIVE CONNECTION'
    : conn === 'demo'
      ? 'DEMO ENVIRONMENT'
      : conn === 'offline'
        ? 'CONNECTION OFFLINE'
        : 'CONNECTING'

  const liveCount = incidents.length.toString().padStart(2, '0')

  return (
    <main className="nova-home">
      <nav className="nova-nav" aria-label="Main navigation">
        <a href="#" className="nova-brand" aria-label="Highway Safety Agent home">
          <span className="nova-brand-mark"><Radar size={20} /></span>
          <span className="nova-brand-type">
            <strong>HRAP<span>.</span></strong>
            <small>HIGHWAY RESPONSE &amp; AWARENESS</small>
          </span>
        </a>
        <div className="nova-nav-right">
          <span className={`nova-connection nova-connection-${conn || 'pending'}`}>
            <i />
            {connectionLabel}
          </span>
          {onToggleTheme && (
            <button
              type="button"
              className="nova-theme-toggle"
              onClick={onToggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          )}
          <button className="nova-nav-cta" onClick={onEnter}>
            Open command <ArrowUpRightIcon />
          </button>
        </div>
      </nav>

      <section className="nova-hero">
        <div className="nova-hero-copy">
          <div className="nova-overline">
            <span className="nova-overline-dot" />
            INTELLIGENCE FOR THE OPEN ROAD
            <span className="nova-overline-year">/ 2026</span>
          </div>

          <h1>
            Seconds<br />
            <span className="nova-headline-outline">matter.</span>
            <span className="nova-headline-accent">We move.</span>
          </h1>

          <p className="nova-hero-description">
            The road never pauses. Your awareness shouldn't either.
            Bring highway incidents, corridor intelligence and response
            decisions into one operational picture.
          </p>

          <div className="nova-hero-actions">
            <button className="nova-button-primary" onClick={onEnter}>
              Enter the command centre <ArrowRight size={19} />
            </button>
            <a className="nova-button-text" href="#nova-capabilities">
              Discover the system <ArrowDownRight size={17} />
            </a>
          </div>

          <div className="nova-proof">
            <div className="nova-proof-icon"><Activity size={16} /></div>
            <div>
              <strong>Awareness to action.</strong>
              <span>One connected operational workspace.</span>
            </div>
          </div>
        </div>

        <div className="nova-visual" aria-label="Illustration of an intelligent highway corridor">
          <div className="nova-visual-top">
            <span><i /> CORRIDOR / 001</span>
            <span>OPERATIONAL VIEW</span>
          </div>

          <div className="nova-orbit nova-orbit-one" />
          <div className="nova-orbit nova-orbit-two" />
          <div className="nova-orbit nova-orbit-three" />

          <div className="nova-scanline" />

          <div className="nova-road-scene">
            <div className="nova-road-glow" />
            <div className="nova-road">
              <div className="nova-road-edge nova-road-edge-left" />
              <div className="nova-road-edge nova-road-edge-right" />
              <div className="nova-road-dash nova-road-dash-one" />
              <div className="nova-road-dash nova-road-dash-two" />
              <div className="nova-road-dash nova-road-dash-three" />
              <div className="nova-road-dash nova-road-dash-four" />
              <div className="nova-road-dash nova-road-dash-five" />
            </div>
            <div className="nova-road-horizon" />
            <div className="nova-road-pin nova-road-pin-one"><span>01</span><i /></div>
            <div className="nova-road-pin nova-road-pin-two"><span>02</span><i /></div>
            <div className="nova-road-pin nova-road-pin-three"><span>03</span><i /></div>
          </div>

          <div className="nova-float-card nova-float-status">
            <div className="nova-card-icon"><Radar size={17} /></div>
            <div>
              <span>CORRIDOR INTELLIGENCE</span>
              <strong>Situational awareness</strong>
            </div>
            <span className="nova-card-live">ON</span>
          </div>

          <div className="nova-float-card nova-float-incident">
            <span className="nova-incident-symbol"><Zap size={16} /></span>
            <div>
              <span>INCIDENT REGISTER</span>
              <strong>{liveCount}<small> recorded</small></strong>
            </div>
            <div className="nova-incident-bars"><i /><i /><i /><i /><i /></div>
          </div>

          <div className="nova-visual-caption">
            <Orbit size={13} />
            <span>SEE THE BIGGER PICTURE</span>
            <span className="nova-caption-line" />
            <span>16° / 80°</span>
          </div>
        </div>

        <div className="nova-hero-index">
          <span>01</span><i /><span>03</span>
        </div>
        <div className="nova-hero-vertical">ENGINEERED FOR THE MOMENT THAT MATTERS</div>
      </section>

      <section className="nova-ribbon" aria-label="Platform status">
        <div className="nova-ribbon-label">THE SYSTEM AT A GLANCE <ArrowDownRight size={15} /></div>
        <div className="nova-ribbon-stat">
          <span className="nova-stat-symbol"><Radio size={17} /></span>
          <div><small>ENVIRONMENT</small><strong>{connectionLabel}</strong></div>
        </div>
        <div className="nova-ribbon-stat">
          <span className="nova-stat-symbol"><Activity size={17} /></span>
          <div><small>INCIDENT RECORDS</small><strong>{liveCount}<em> / TOTAL</em></strong></div>
        </div>
        <div className="nova-ribbon-stat">
          <span className="nova-stat-symbol"><ShieldCheck size={17} /></span>
          <div><small>OPERATIONAL MODE</small><strong>Incident command</strong></div>
        </div>
      </section>

      <section className="nova-capabilities" id="nova-capabilities">
        <div className="nova-section-intro">
          <div>
            <span className="nova-section-kicker">01 — WHAT WE BRING TO THE ROAD</span>
            <h2>
              Less time<br />
              <span>finding the signal.</span>
            </h2>
          </div>
          <p>
            A single operational picture, from incident detection to the
            decisions that follow. Designed to make complexity legible
            when every second counts.
          </p>
        </div>

        <div className="nova-capability-grid">
          {capabilities.map(({ number, icon: Icon, tag, title, text, accent }) => (
            <article className={`nova-capability nova-capability-${accent}`} key={number}>
              <div className="nova-capability-top">
                <span>{number} <i>/</i> 03</span>
                <Icon size={23} strokeWidth={1.5} />
              </div>
              <span className="nova-capability-tag">{tag}</span>
              <h3>{title}</h3>
              <p>{text}</p>
              <div className="nova-capability-bottom">
                <span>EXPLORE CAPABILITY</span>
                <MoveUpRight size={17} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="nova-manifesto">
        <div className="nova-manifesto-mark">“</div>
        <div>
          <span className="nova-section-kicker">02 — THE PRINCIPLE</span>
          <h2>Clarity is not a luxury.<br /><span>It is the intervention.</span></h2>
        </div>
        <button className="nova-manifesto-cta" onClick={onEnter}>
          Experience the workspace <ArrowRight size={18} />
        </button>
        <div className="nova-manifesto-decoration" aria-hidden="true">HRAP</div>
      </section>

      <footer className="nova-footer">
        <a href="#" className="nova-footer-brand">HRAP<span>.</span></a>
        <span>HIGHWAY SAFETY AGENT · 2026</span>
        <span className="nova-footer-note">Operational decision support. Follow authorised emergency procedures.</span>
      </footer>
    </main>
  )
}

function ArrowUpRightIcon() {
  return <MoveUpRight size={16} />
}
