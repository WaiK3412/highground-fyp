/**
 * Screen 01 — the public landing page, for visitors who are not signed in.
 * Layout and styles are the frozen design's; the wording describes what the
 * delivered system does, and the figures carry their sources (report Chapter 1).
 */

import { Icon, PATHS } from '../icons'
import { useDocumentTitle } from '../useDocumentTitle'
import Contours from '../components/Contours'
import HeroScene from '../components/landing/HeroScene'
import PublicAppeals from '../components/landing/PublicAppeals'
import '../styles/landing.css'

const DOSM_2025 = {
  name: 'DOSM, 2025',
  url: 'https://www.dosm.gov.my/portal-main/release-content/special-report-on-impact-of-floods-in-malaysia-2024',
}
const IFRC_2024 = {
  name: 'IFRC, 2024',
  url: 'https://reliefweb.int/report/malaysia/malaysia-flood-2024-dref-operation-mdrmy011',
}

const STATS = [
  { value: 'RM933.4m', label: 'flood losses recorded in Malaysia in 2024', source: DOSM_2025, hero: true },
  { value: '40,922', label: 'families displaced in the 2024 Northeast Monsoon floods', source: IFRC_2024 },
  { value: '633', label: 'temporary evacuation centres opened', source: IFRC_2024 },
  { value: '65%', label: 'of flood victims in a DOSM case study received help within 48 hours', source: DOSM_2025 },
]

const STEPS = [
  {
    title: 'Submit your request',
    text: 'Tell us what your household needs — cleanup, repairs, essential items — and add photos of the damage, from any phone.',
  },
  {
    title: 'Checked and prioritised',
    text: 'A district officer checks the request and it gets a priority class from published rules. Relief organisations claim the help they can give, so no one is visited twice.',
  },
  {
    title: 'Follow it to the end',
    text: 'See every step of your case, get notified when it is verified, taken on and finished, and confirm when the work is done.',
  },
]

const ROLES = [
  {
    icon: PATHS.home,
    tone: 'icon-bg--teal',
    title: 'Residents',
    text: 'Request recovery help for your household, answer questions from the district office, and track each case until the work is confirmed.',
  },
  {
    icon: PATHS.org,
    tone: 'icon-bg--info',
    title: 'Relief organisations',
    text: 'See verified cases in priority order and on a map, claim the help your team can give, assign tasks and record progress with photos.',
  },
  {
    icon: PATHS.queue,
    tone: 'icon-bg--teal',
    title: 'District officers',
    text: 'Check requests for your district, review possible duplicates, and see why each case has its priority class.',
  },
]

function SectionHead({ eyebrow, title, children }) {
  return (
    <div className="section-head">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {children}
    </div>
  )
}

export default function Landing({ onShowLogin, onShowRegister, onDonate }) {
  useDocumentTitle('Flood recovery coordination')

  return (
    <div className="landing">
      <header className="site-header">
        <div className="container">
          <a className="logo" href="/" aria-label="HighGround home">
            <span className="logo__mark"><Icon path={PATHS.logo} strokeWidth={2} /></span>
            <span><span className="logo__name">HighGround</span></span>
          </a>
          <nav className="site-nav" aria-label="Landing page">
            <a className="site-nav__section" href="#how">How it works</a>
            <a className="site-nav__section" href="#roles">Who it is for</a>
            <a className="site-nav__section" href="#community">Supplies needed</a>
            <button className="btn btn--secondary btn--sm" onClick={onShowLogin}>Log in</button>
            <button className="btn btn--primary btn--sm" onClick={onShowRegister}>Get help</button>
          </nav>
        </div>
      </header>

      <main>
        <section className="hero">
          <Contours
            className="hero-contours"
            stroke="#BC6C4F"
            scales={[[1, 0.16], [0.8, 0.22], [0.6, 0.28], [0.42, 0.34], [0.26, 0.4]]}
          />
          <div className="container">
            <div>
              <h1>After the flood,<br />help finds <span className="accent">your home</span>.</h1>
              <p className="sub">
                HighGround brings flood-affected households in Malaysia together with the district
                officers and relief organisations coordinating cleanup, repair and essential items —
                in one shared place.
              </p>
              <div className="row" style={{ flexWrap: 'wrap' }}>
                <button className="btn btn--primary btn--big" onClick={onShowRegister}>
                  Request assistance <Icon path={PATHS.arrow} strokeWidth={2} />
                </button>
                <button className="btn btn--secondary btn--big" onClick={onShowLogin}>Log in</button>
              </div>
              <p className="text-sm text-muted" style={{ marginTop: '1.6rem' }}>
                Free for affected households · Works in any phone browser
              </p>
            </div>
            <HeroScene />
          </div>
        </section>

        <section style={{ background: 'var(--white)', padding: 'var(--sp-32) 0 var(--sp-64)' }} aria-label="Flood figures">
          <div className="container">
            <div className="stat-strip">
              {STATS.map((stat) => (
                <div key={stat.label} className={`stat-strip__item${stat.hero ? ' stat-strip__item--hero' : ''}`}>
                  <div className="stat-strip__value">{stat.value}</div>
                  <div className="stat-strip__label">{stat.label}</div>
                  <span className="stat-source">
                    Source: <a href={stat.source.url} target="_blank" rel="noreferrer">{stat.source.name}</a>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="how">
          <div className="container">
            <SectionHead eyebrow="How it works" title="From request to recovery in three steps" />
            <div className="grid-3">
              {STEPS.map((step, index) => (
                <div key={step.title} className="how-step">
                  <div className="how-step__num"><span>{index + 1}</span></div>
                  <h3 style={{ marginBottom: '0.8rem' }}>{step.title}</h3>
                  <p className="text-sm text-muted">{step.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="roles" className="roles">
          <div className="container">
            <SectionHead eyebrow="One platform, every responder" title="Built for everyone in the recovery effort" />
            <div className="grid-3">
              {ROLES.map((role) => (
                <div key={role.title} className="card card--flat">
                  <span className={`stat-card__icon ${role.tone}`} style={{ marginBottom: '1.6rem' }}>
                    <Icon path={role.icon} />
                  </span>
                  <h3 style={{ marginBottom: '0.8rem' }}>{role.title}</h3>
                  <p className="text-sm text-muted">{role.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="community" className="community">
          <div className="container">
            <SectionHead eyebrow="Bantuan komuniti · Community help" title="Not flooded? You can still help">
              <p className="text-sm text-muted" style={{ marginTop: '0.8rem' }}>
                Relief organisations list the items they need and where to drop them off. HighGround
                never collects money — record what you will bring, and the organisation confirms when it arrives.
              </p>
            </SectionHead>
            <PublicAppeals onDonate={onDonate} />
          </div>
        </section>

        <section className="cta-band batik-accent--light">
          <div className="container">
            <h2>Affected by the floods?</h2>
            <p style={{ marginBottom: '2.4rem', opacity: 0.9 }}>Open a recovery request today — it is free.</p>
            <button className="btn btn--big" style={{ background: 'var(--white)', color: 'var(--teal-800)' }} onClick={onShowRegister}>
              Request assistance now
            </button>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container">
          <p className="text-sm">
            HighGround — flood recovery coordination for Malaysia, a final-year project prototype. In an
            emergency, call 999. HighGround is for recovery after a flood, not rescue.
          </p>
        </div>
      </footer>
    </div>
  )
}
