/**
 * Screen 07 — Case queue, the List tab of its Map/List/Board toggle.
 * Cases arrive from /api/cases/ already narrowed by role on the server.
 */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'verified', label: 'Verified' },
  { value: 'claimed', label: 'Claimed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'submitted', label: 'Submitted' },
]

// Slim, warm-toned scrollbars on the panels that scroll, plus a gutter so the
// cards are not pressed up against the bar. Set here rather than in styles.css:
// the design contract is frozen and never styles scrollbars, so this stays a
// code-level choice instead of a change to the design.
const SCROLL_PANE = {
  scrollbarWidth: 'thin',
  scrollbarColor: 'var(--grey-300) transparent',
  paddingRight: 'var(--sp-16)',
}

function scoreClass(band) {
  if (band === 'High') return 'score score--high score--sm'
  if (band === 'Medium') return 'score score--medium score--sm'
  return 'score score--low score--sm'
}

function CaseCard({ item, onOpen, onClaim, selected, user, busy }) {
  // Screen 07 puts "Claim case" on the card, not behind the detail panel.
  const canClaim =
    user.role === 'ngo_volunteer' && item.status === 'verified' && !item.claimed_by
  const canDecide = user.role === 'disaster_officer' && item.status === 'submitted'

  return (
    <div className={`ops-card${selected ? ' ops-card--selected' : ''}`}>
      <div className="row--between">
        <span className="title">#{item.reference}</span>
        <span className={scoreClass(item.priority_band)}>{item.score_total}</span>
      </div>
      <span className="meta">
        {item.damage_category_display} · {item.village} · household of {item.household_size} ·
        waiting {item.days_waiting} {item.days_waiting === 1 ? 'day' : 'days'}
      </span>
      <div className="row" style={{ flexWrap: 'wrap', gap: '0.8rem' }}>
        <span className="badge badge--verified">{item.status_display}</span>
        {item.claimed_by && <span className="filter-chip">Claimed by {item.claimed_by}</span>}
      </div>
      <div className="row" style={{ gap: '0.8rem' }}>
        {canClaim && (
          <button
            className="btn btn--primary btn--sm"
            disabled={busy}
            onClick={() => onClaim(item.id)}
          >
            {busy ? 'Claiming…' : 'Claim case'}
          </button>
        )}
        <button
          className={`btn btn--sm ${canClaim ? 'btn--ghost' : 'btn--primary'}`}
          onClick={() => onOpen(item.id)}
        >
          {canDecide ? 'Review & decide' : 'View details'}
        </button>
      </div>
    </div>
  )
}

function CaseActions({ detail, user, onDone }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [note, setNote] = useState('')

  const canClaim =
    user.role === 'ngo_volunteer' && detail.status === 'verified' && !detail.claimed_by
  const canDecide = user.role === 'disaster_officer' && detail.status === 'submitted'

  if (!canClaim && !canDecide) return null

  async function run(action) {
    setError(null)
    setBusy(true)
    try {
      await action()
      await onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 'var(--sp-16)', borderTop: '1px solid var(--grey-200)', paddingTop: 'var(--sp-16)' }}>
      {error && (
        <div
          role="alert"
          style={{
            background: 'var(--danger-100)',
            color: 'var(--danger-600)',
            padding: '0.8rem 1rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--fs-12)',
            fontWeight: 600,
            marginBottom: 'var(--sp-12)',
          }}
        >
          {error}
        </div>
      )}

      {canClaim && (
        <button
          className="btn btn--primary btn--full"
          disabled={busy}
          onClick={() => run(() => api.claimCase(detail.id))}
        >
          {busy ? 'Claiming…' : 'Claim this case for my organisation'}
        </button>
      )}

      {canDecide && (
        <div className="stack" style={{ gap: '1rem' }}>
          <div className="field">
            <label htmlFor="note">Note to the household</label>
            <input
              id="note"
              className="input"
              placeholder="Required when asking for more or rejecting"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap' }}>
            <button
              className="btn btn--primary btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'verified', note))}
            >
              Verify
            </button>
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'needs_info', note))}
            >
              Ask for more
            </button>
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'rejected', note))}
            >
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function ScorePanel({ detail, onClose, user, onDone }) {
  if (!detail) return null
  return (
    <aside className="card" style={{ padding: 'var(--sp-20)' }}>
      <div className="row--between">
        <h2 style={{ margin: 0 }}>#{detail.reference}</h2>
        <button className="btn btn--ghost btn--sm" onClick={onClose}>
          Close
        </button>
      </div>

      <p className="text-sm text-muted" style={{ marginTop: 'var(--sp-8)' }}>
        {detail.description}
      </p>

      <div className="row--between" style={{ marginTop: 'var(--sp-16)' }}>
        <span className="text-strong">Priority score</span>
        <span className={scoreClass(detail.priority_band)}>{detail.score_total}</span>
      </div>

      <div className="stack" style={{ gap: '0.8rem', marginTop: 'var(--sp-12)' }}>
        {detail.score_components.map((component) => (
          <div key={component.name} className="score-row">
            <span>{component.name}</span>
            <span className="pts">+{component.points}</span>
            <span className="text-xs text-muted" style={{ flexBasis: '100%' }}>
              {component.reason}
            </span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 'var(--sp-16)' }}>
        <span className="text-xs text-muted">
          {detail.location.precision === 'exact' ? 'Exact location' : 'Approximate location'}
        </span>
        <div className="text-sm">{detail.location.address}</div>
        {detail.location.precision === 'village' && (
          <div className="text-xs text-muted" style={{ marginTop: '0.4rem' }}>
            Exact coordinates are released to the district office and the claiming organisation only.
          </div>
        )}
      </div>

      <CaseActions detail={detail} user={user} onDone={onDone} />
    </aside>
  )
}

export default function CaseQueue({ user, onLogout, onNavigate }) {
  const [unread, setUnread] = useState(0)
  useDocumentTitle('Case queue')
  const [cases, setCases] = useState([])
  const [stats, setStats] = useState(null)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    api
      .notifications()
      .then((data) => setUnread(data.unread))
      .catch(() => setUnread(0))
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([api.cases({ status, q: search }), api.stats()])
      .then(([list, s]) => {
        if (cancelled) return
        setCases(list.results)
        setStats(s)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [status, search, reloadKey])

  // Re-fetch after an action so the screen shows what the server recorded,
  // not what we assumed it would record.
  async function refresh() {
    setReloadKey((n) => n + 1)
    if (detail) setDetail(await api.caseDetail(detail.id))
  }

  const [claimingId, setClaimingId] = useState(null)
  const [claimError, setClaimError] = useState(null)
  const [notice, setNotice] = useState(null)

  async function claimFromCard(id) {
    setClaimError(null)
    setNotice(null)
    setClaimingId(id)
    try {
      const claimed = await api.claimCase(id)
      // The button vanishes once the case is held; without a message that
      // reads as nothing having happened.
      setNotice(
        `#${claimed.reference} is now assigned to ${claimed.claimed_by}. ` +
          `It is locked to other organisations and the change is in the audit log.`,
      )
      await refresh()
    } catch (err) {
      setClaimError(err.message)
    } finally {
      setClaimingId(null)
    }
  }

  const initials = user.full_name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#queue" onClick={(e) => e.preventDefault()}>
          <span className="logo__mark">
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0"
              />
            </svg>
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">{user.role_display}</span>
          </span>
        </a>

        <nav className="side-nav">
          <a href="#queue" className="active" onClick={(e) => e.preventDefault()}>
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z"
              />
            </svg>
            Case queue
            {stats && <span className="side-nav__count">{stats.total}</span>}
          </a>

          <a href="#tasks" onClick={(e) => e.preventDefault()}>
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z"
              />
            </svg>
            Task board
          </a>

          <a
            href="#notifications"
            onClick={(e) => {
              e.preventDefault()
              onNavigate('notifications')
            }}
          >
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
              />
            </svg>
            Notifications
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>

          <a
            href="#rules"
            onClick={(e) => {
              e.preventDefault()
              onNavigate('rules')
            }}
          >
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 6.75A2.25 2.25 0 015.25 4.5h13.5A2.25 2.25 0 0121 6.75v10.5A2.25 2.25 0 0118.75 19.5H5.25A2.25 2.25 0 013 17.25V6.75zM7.5 9h9M7.5 12h9M7.5 15h5.25"
              />
            </svg>
            How scoring works
          </a>

          <span className="side-nav__label">Organisation</span>
          <a href="#org" onClick={(e) => e.preventDefault()}>
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.75c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
              />
            </svg>
            {user.organization || 'No organisation'}
          </a>
        </nav>

        <div className="sidebar__user">
          <span className="avatar avatar--info">{initials}</span>
          <div>
            <div className="text-sm text-strong">{user.full_name}</div>
            <button
              className="text-xs text-muted"
              onClick={onLogout}
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="main main--vp">
        <div className="page-header">
          <div>
            <h1>Case queue</h1>
            <p>
              Recovery cases visible to you as {user.role_display.toLowerCase()}. Priority is computed
              from the published rubric v3.0.
            </p>
          </div>
        </div>

        {stats && (
          <div className="row" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
            <span className="map-kpi">
              <span className="map-kpi__value">{stats.total}</span> visible to you
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value" style={{ color: 'var(--danger-600)' }}>
                {stats.high}
              </span>{' '}
              high priority
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value" style={{ color: 'var(--teal-700)' }}>
                {stats.unclaimed}
              </span>{' '}
              unclaimed
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value">{stats.in_progress}</span> in progress
            </span>
          </div>
        )}

        <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', margin: 'var(--sp-16) 0' }}>
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.value}
              className={`filter-chip${status === filter.value ? ' filter-chip--active' : ''}`}
              onClick={() => setStatus(filter.value)}
              style={{ cursor: 'pointer', border: 0 }}
            >
              {filter.label}
            </button>
          ))}
          <input
            className="input"
            style={{ maxWidth: '24rem' }}
            placeholder="Search reference, village…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* vp-fill claims the rest of the viewport and each column scrolls on
            its own, so the filter bar and stat strip stay pinned while a long
            queue or a long score panel scrolls independently. */}
        <div
          className="vp-fill"
          style={{
            display: 'grid',
            gridTemplateColumns: detail ? '1fr 1fr' : '1fr',
            gap: 'var(--sp-16)',
          }}
        >
          <div className="stack vp-scroll" style={{ gap: 'var(--sp-12)', ...SCROLL_PANE }}>
            {notice && (
              <div className="banner banner--info">
                <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span className="body">
                  <span className="title">Case claimed.</span>
                  <br />
                  {notice}
                </span>
              </div>
            )}
            {claimError && (
              <div
                role="alert"
                style={{
                  background: 'var(--danger-100)',
                  color: 'var(--danger-600)',
                  padding: '1rem 1.2rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--fs-14)',
                  fontWeight: 600,
                }}
              >
                {claimError}
              </div>
            )}
            {loading && <p className="text-muted">Loading cases…</p>}
            {!loading && cases.length === 0 && (
              <p className="text-muted">No cases match this filter.</p>
            )}
            {cases.map((item) => (
              <CaseCard
                key={item.id}
                item={item}
                user={user}
                busy={claimingId === item.id}
                selected={detail?.id === item.id}
                onClaim={claimFromCard}
                onOpen={(id) => api.caseDetail(id).then(setDetail)}
              />
            ))}
          </div>

          {detail && (
            <div className="stack vp-scroll" style={{ gap: 'var(--sp-12)', ...SCROLL_PANE }}>
              <ScorePanel
                detail={detail}
                user={user}
                onDone={refresh}
                onClose={() => setDetail(null)}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
