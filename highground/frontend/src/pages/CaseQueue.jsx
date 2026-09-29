/**
 * Screen 07 — Case queue, the List tab of its Map/List/Board toggle.
 * Cases arrive from /api/cases/ already narrowed by role on the server.
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import CaseMap from './CaseMap'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'verified', label: 'Verified' },
  { value: 'claimed', label: 'Claimed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'submitted', label: 'Submitted' },
]
const BAND_FILTERS = [
  { value: '', label: 'All' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
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
  if (band === 'Low') return 'score score--low score--sm'
  return 'score score--neutral score--sm'
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
        <span className={scoreClass(item.priority_band)} aria-label={item.score_total == null ? 'Not scored yet' : `${item.priority_band} priority, score ${item.score_total}`}>
          {item.score_total ?? '—'}
        </span>
      </div>
      <span className="meta">
        {item.damage_category_display} · {item.village} · household of {item.household_size} ·
        waiting {item.days_waiting} {item.days_waiting === 1 ? 'day' : 'days'}
      </span>
      <div className="row" style={{ flexWrap: 'wrap', gap: '0.8rem' }}>
        <span className="badge badge--verified">{item.status_display}</span>
        {user.role === 'disaster_officer' && item.has_open_duplicate && (
          <span className="badge badge--duplicate">Possible duplicate</span>
        )}
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

function CaseActions({ detail, user, onDone, onOpenDuplicate }) {
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
      setError({ message: err.message, code: err.code, matchIds: err.data?.duplicate_match_ids || [] })
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
          {error.code === 'duplicate_check_pending'
            ? 'The duplicate check has not finished. Refresh this case before trying to verify it.'
            : error.code === 'duplicate_review_required'
              ? 'A possible duplicate needs officer review before this case can be verified.'
              : error.code === 'case_linked_duplicate'
                ? 'This case was closed as a confirmed duplicate and cannot be verified again.'
                : error.message}
          {error.code === 'duplicate_check_pending' && (
            <button className="btn btn--ghost btn--sm" onClick={async () => {
              setError(null)
              try { await onDone() } catch (err) { setError({ message: err.message, matchIds: [] }) }
            }}>Refresh case</button>
          )}
          {error.matchIds.map((id) => (
            <button key={id} className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(id, detail.id)}>
              Open duplicate review #{id}
            </button>
          ))}
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

// Each criterion's share of the total, in the design's teal steps (screen 10).
const SEGMENT_TONES = ['t900', 't800', 't700', 't600', 't500', 't300']

function scoreOutOf(components) {
  return components.reduce((sum, component) => sum + component.weight, 0) || 100
}

/**
 * Screen 08's breakdown: every criterion's points against its weight, then the
 * total and the rubric version that produced it (FR22). The small line under
 * each bar is the engine's stored explanation, shown as recorded.
 */
function ScoreBreakdown({ detail }) {
  if (detail.score_total == null) {
    return (
      <p className="text-sm text-muted" style={{ marginTop: 'var(--sp-16)' }}>
        Not scored yet — a case is scored when an officer verifies it.
      </p>
    )
  }
  const components = detail.score_components || []
  const outOf = scoreOutOf(components)
  return (
    <div style={{ marginTop: 'var(--sp-16)' }}>
      <div className="row--between">
        <span className="text-strong">Priority score</span>
        <span className={scoreClass(detail.priority_band)}>{detail.score_total}</span>
      </div>
      {components.length > 0 && (
        <div className="stack" style={{ gap: '1rem', marginTop: 'var(--sp-12)' }}>
          {components.map((component) => (
            <div key={component.name}>
              <div className="score-row">
                <span className="score-row__name">{component.name}</span>
                <span className="bar progress" aria-hidden="true">
                  <span
                    className="progress__fill"
                    style={{
                      display: 'block',
                      width: `${component.weight ? Math.round((component.points / component.weight) * 100) : 0}%`,
                    }}
                  />
                </span>
                <span className="pts">
                  +{component.points}
                  <span className="text-xs text-muted"> / {component.weight}</span>
                </span>
              </div>
              {component.reason && (
                <div className="text-xs text-muted">{component.reason.replaceAll('_', ' ')}</div>
              )}
            </div>
          ))}
        </div>
      )}
      <hr className="divider" style={{ margin: '1.2rem 0' }} />
      <div className="row--between">
        <span className="text-xs text-muted">
          {detail.rubric_label ? `Rubric ${detail.rubric_label}` : 'Published rubric'} · rule-based,
          reviewed by officers
        </span>
        <span className="text-strong">
          {detail.score_total}
          <span className="text-sm text-muted">/{outOf}</span>
        </span>
      </div>
    </div>
  )
}

/**
 * The case card that opens over the map when a pin is clicked (screen 10's
 * popover), so the map stays in view. It reads the same detail response as
 * the side panel, so it shows nothing the viewer's role may not see.
 */
function MapCaseCard({ detail, user, onOpen, onClose, onOpenDuplicate }) {
  const components = detail.score_components || []
  const outOf = scoreOutOf(components)
  const canDecide = user.role === 'disaster_officer' && detail.status === 'submitted'
  return (
    <div className="ops-popover case-map__popover" role="dialog" aria-label={`Case ${detail.reference}`}>
      <div className="row--between" style={{ alignItems: 'flex-start' }}>
        <div>
          <div className="text-strong" style={{ fontSize: 'var(--fs-16)' }}>#{detail.reference}</div>
          <div className="text-xs text-muted">
            {detail.damage_category_display} · {detail.village}
          </div>
        </div>
        {detail.score_total != null && (
          <span className={scoreClass(detail.priority_band)}>{detail.score_total}</span>
        )}
      </div>
      <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap' }}>
        <span className="badge badge--verified">{detail.status_display}</span>
        {user.role === 'disaster_officer' && detail.has_open_duplicate && (
          <span className="badge badge--duplicate">Possible duplicate</span>
        )}
        <span className="text-xs text-muted">
          {detail.claimed_by ? `Claimed by ${detail.claimed_by}` : 'Unclaimed'} · waiting{' '}
          {detail.days_waiting} {detail.days_waiting === 1 ? 'day' : 'days'}
        </span>
      </div>
      {components.length > 0 ? (
        <div>
          <div className="score-stack" title={`Score breakdown — rubric ${detail.rubric_label || ''}`}>
            {components.map((component, index) => (
              <span
                key={component.name}
                className={`score-stack__seg score-stack__seg--${SEGMENT_TONES[index % SEGMENT_TONES.length]}`}
                style={{ width: `${(component.points / outOf) * 100}%` }}
                title={`${component.name} · ${component.points}`}
              />
            ))}
          </div>
          <div className="text-xs text-muted" style={{ marginTop: '0.6rem' }}>
            {detail.score_total} / {outOf}
            {detail.rubric_label ? ` · rubric ${detail.rubric_label}` : ''} —{' '}
            {components.map((component) => `${component.key} ${component.points}`).join(' · ')}
          </div>
        </div>
      ) : (
        detail.score_total == null && (
          <div className="text-xs text-muted">Not scored yet — scored when an officer verifies it.</div>
        )
      )}
      <div className="text-xs text-muted">
        {detail.location.precision === 'exact'
          ? detail.location.address
          : 'Village-level location only'}
      </div>
      <div className="row" style={{ gap: '0.8rem' }}>
        <button className="btn btn--primary btn--sm" onClick={onOpen}>
          {canDecide ? 'Review & decide' : 'Open full details'}
        </button>
        <button className="btn btn--ghost btn--sm" onClick={onClose}>
          Close
        </button>
      </div>
      {user.role === 'disaster_officer' && detail.duplicate_review?.open_match_ids?.length > 0 && (
        <button className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(detail.duplicate_review.open_match_ids[0], detail.id)}>
          Open duplicate review
        </button>
      )}
      {user.role === 'disaster_officer' && detail.duplicate_review?.confirmed_match_id && (
        <button className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(detail.duplicate_review.confirmed_match_id, detail.id)}>
          Open confirmed duplicate review
        </button>
      )}
    </div>
  )
}

function ScorePanel({ detail, onClose, user, onDone, onOpenDuplicate }) {
  if (!detail) return null
  const summaryOnly = detail.detail_access === 'summary'
  return (
    <aside className="card" style={{ padding: 'var(--sp-20)' }}>
      <div className="row--between">
        <h2 style={{ margin: 0 }}>#{detail.reference}</h2>
        <button className="btn btn--ghost btn--sm" onClick={onClose}>
          Close
        </button>
      </div>

      {summaryOnly ? (
        <div className="banner banner--info" style={{ marginTop: 'var(--sp-12)' }}>
          <span className="body">
            <span className="title">Household details are protected.</span>
            <br />
            This coordination summary is enough to assess capacity. Photos, vulnerability details,
            case history and the exact address are released only to the claiming organisation.
          </span>
        </div>
      ) : (
        <p className="text-sm text-muted" style={{ marginTop: 'var(--sp-8)' }}>
          {detail.description}
        </p>
      )}

      <ScoreBreakdown detail={detail} />

      {user.role === 'disaster_officer' && detail.duplicate_review?.open_match_ids?.length > 0 && (
        <div className="row" style={{ flexWrap: 'wrap', marginTop: 'var(--sp-12)' }}>
          <span className="badge badge--duplicate">Possible duplicate</span>
          {detail.duplicate_review.open_match_ids.map((id) => (
            <button key={id} className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(id, detail.id)}>
              Review pair #{id}
            </button>
          ))}
        </div>
      )}
      {user.role === 'disaster_officer' && detail.duplicate_review?.confirmed_match_id && (
        <button className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(detail.duplicate_review.confirmed_match_id, detail.id)}>
          Open confirmed duplicate review
        </button>
      )}

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

      <CaseActions detail={detail} user={user} onDone={onDone} onOpenDuplicate={onOpenDuplicate} />
    </aside>
  )
}

export default function CaseQueue({ user, onLogout, onNavigate, onOpenDuplicate, duplicateCount }) {
  const [unread, setUnread] = useState(0)
  useDocumentTitle('Case queue')
  const [cases, setCases] = useState([])
  const [stats, setStats] = useState(null)
  const [status, setStatus] = useState('')
  const [band, setBand] = useState('')
  const [search, setSearch] = useState('')
  const [listError, setListError] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  const [reloadKey, setReloadKey] = useState(0)
  // List stays the default: it works without map tiles and holds every case.
  const [view, setView] = useState('list')
  const [mapData, setMapData] = useState(null)
  const [mapError, setMapError] = useState(null)
  const [mapLoading, setMapLoading] = useState(false)
  // The case whose card is open over the map (a full detail response).
  const [mapCase, setMapCase] = useState(null)
  const selectionVersion = useRef(0)

  function invalidateQueue({ keepDetail = false } = {}) {
    selectionVersion.current += 1
    setMapCase(null)
    if (!keepDetail) setDetail(null)
    setLoading(true)
    setListError(null)
    setStats(null)
    setCases([])
    setMapLoading(view === 'map')
    setMapData(null)
    setMapError(null)
  }

  useEffect(() => {
    api
      .notifications()
      .then((data) => setUnread(data.unread))
      .catch(() => setUnread(0))
  }, [])

  useEffect(() => {
    let cancelled = false
    const params = { status, band, q: search }
    Promise.all([api.cases(params), api.stats(params)])
      .then(([list, s]) => {
        if (cancelled) return
        setCases(list.results)
        setStats(s)
      })
      .catch((err) => !cancelled && setListError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [status, band, search, reloadKey])

  // The map is fetched only when shown, with the same filters as the list.
  useEffect(() => {
    if (view !== 'map') return undefined
    let cancelled = false
    api
      .caseMap({ status, band, q: search })
      .then((data) => {
        if (cancelled) return
        setMapData(data)
        setMapError(null)
      })
      .catch((err) => !cancelled && setMapError(err.message))
      .finally(() => !cancelled && setMapLoading(false))
    return () => {
      cancelled = true
    }
  }, [view, status, band, search, reloadKey])

  const openCase = (id) => {
    const version = selectionVersion.current
    return api.caseDetail(id).then((result) => {
      if (selectionVersion.current === version) setDetail(result)
    })
  }
  // On the map, a pin opens a card over the map; the side panel is one click on.
  const openMapCase = (id) => {
    const version = selectionVersion.current
    return api
      .caseDetail(id)
      .then((result) => {
        if (selectionVersion.current === version) setMapCase(result)
      })
      .catch((err) => {
        if (selectionVersion.current === version) setMapError(err.message)
      })
  }
  const closeMapCase = () => setMapCase(null)
  // A village marker stands for cases the list can show; go there.
  const showVillage = (name) => {
    invalidateQueue()
    setSearch(name)
    setReloadKey((n) => n + 1)
    setView('list')
  }

  // Escape closes the map card, as it would any dialog.
  useEffect(() => {
    if (!mapCase) return undefined
    const onKey = (event) => event.key === 'Escape' && setMapCase(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mapCase])

  // Re-fetch after an action so the screen shows what the server recorded,
  // not what we assumed it would record.
  async function refresh() {
    invalidateQueue({ keepDetail: true })
    const version = selectionVersion.current
    setReloadKey((n) => n + 1)
    if (detail) {
      const current = await api.caseDetail(detail.id)
      if (selectionVersion.current === version) setDetail(current)
    }
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
            <span className="logo__role">
              {user.role === 'ngo_volunteer' ? 'NGO responder' : user.role_display}
            </span>
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

          {user.role === 'disaster_officer' && (
            <a href="#duplicates" onClick={(e) => { e.preventDefault(); onNavigate('duplicates') }}>
              <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 8.25V6a2.25 2.25 0 00-2.25-2.25H6A2.25 2.25 0 003.75 6v8.25A2.25 2.25 0 006 16.5h2.25m8.25-8.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-7.5A2.25 2.25 0 018.25 18v-7.5a2.25 2.25 0 012.25-2.25h6z" />
              </svg>
              Duplicate review
              {duplicateCount !== null && <span className="side-nav__count">{duplicateCount}</span>}
            </a>
          )}

          {user.role === 'ngo_volunteer' && <a
            href="#tasks"
            onClick={(e) => {
              e.preventDefault()
              onNavigate('tasks')
            }}
          >
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z"
              />
            </svg>
            Task board
          </a>}

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
          <span className="side-nav__item side-nav__item--static">
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.75c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
              />
            </svg>
            {user.organization || 'No organisation'}
          </span>
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
              Recovery cases visible to you as{' '}
              {user.role === 'ngo_volunteer' ? 'an NGO responder' : `a ${user.role_display.toLowerCase()}`}. Priority is computed
              from the rubric version that scored each case.
            </p>
          </div>
          <div className="view-toggle" role="group" aria-label="Queue view">
            {[['list', 'List'], ['map', 'Map']].map(([key, label]) => (
              <a
                key={key}
                href={`#${key}`}
                className={view === key ? 'active' : undefined}
                aria-pressed={view === key}
                onClick={(e) => {
                  e.preventDefault()
                  if (view === key) return
                  selectionVersion.current += 1
                  setMapCase(null)
                  if (key === 'map') {
                    setMapLoading(true)
                    setMapData(null)
                    setMapError(null)
                  }
                  setView(key)
                }}
              >
                {label}
              </a>
            ))}
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

        <div className="case-queue__filters">
          <div className="case-queue__filter-group" role="group" aria-label="Case status">
            <span className="case-queue__filter-label" aria-hidden="true">Status</span>
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`filter-chip${status === filter.value ? ' filter-chip--active' : ''}`}
                aria-pressed={status === filter.value}
                onClick={() => {
                  if (status === filter.value) return
                  invalidateQueue()
                  setStatus(filter.value)
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="case-queue__filter-group" role="group" aria-label="Priority band">
            <span className="case-queue__filter-label" aria-hidden="true">Priority</span>
            {BAND_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`filter-chip${band === filter.value ? ' filter-chip--active' : ''}`}
                aria-pressed={band === filter.value}
                onClick={() => {
                  if (band === filter.value) return
                  invalidateQueue()
                  setBand(filter.value)
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            className="input"
            style={{ maxWidth: '24rem' }}
            aria-label="Search cases by reference or village"
            placeholder="Search reference, village…"
            value={search}
            onChange={(e) => {
              invalidateQueue()
              setSearch(e.target.value)
            }}
          />
        </div>
        {band && <p className="case-queue__filter-note">Cases awaiting scoring appear under Priority: All.</p>}

        {/* vp-fill claims the rest of the viewport and each column scrolls on
            its own, so the filter bar and stat strip stay pinned while a long
            queue or a long score panel scrolls independently. */}
        <div
          className={`vp-fill case-queue__workspace${detail ? ' case-queue__workspace--split' : ''}`}
          style={{
            display: 'grid',
            gap: 'var(--sp-16)',
          }}
        >
          {view === 'map' ? (
            <div className="stack" style={{ gap: 'var(--sp-12)', minHeight: 0 }}>
              {mapLoading && <p role="status" className="text-sm text-muted">Updating map…</p>}
              {mapError && (
                <p role="alert" className="text-sm" style={{ color: 'var(--danger-600)' }}>
                  {mapError}
                </p>
              )}
              {mapData?.unmapped > 0 &&
                (mapData.points.length > 0 || mapData.areas.length > 0) && (
                <p className="text-sm text-muted">
                  {mapData.unmapped} {mapData.unmapped === 1 ? 'case has' : 'cases have'} no mapped
                  location yet — the list shows {mapData.unmapped === 1 ? 'it' : 'them'}.
                </p>
              )}
              {!mapLoading && !mapError && mapData &&
                mapData.points.length === 0 && mapData.areas.length === 0 && (
                  <p role="status" className="text-sm text-muted">
                    {mapData.unmapped > 0
                      ? `${mapData.unmapped} matching ${mapData.unmapped === 1 ? 'case has' : 'cases have'} no mapped location. ${mapData.unmapped === 1 ? 'It is' : 'They are'} in List view.`
                      : 'No cases match this filter.'}
                  </p>
                )}
              <CaseMap
                points={mapData?.points || []}
                areas={mapData?.areas || []}
                isOfficer={user.role === 'disaster_officer'}
                selectedId={mapCase?.id}
                onOpenCase={openMapCase}
                onOpenArea={showVillage}
                onMapClick={closeMapCase}
              >
                {mapCase && (
                  <MapCaseCard
                    detail={mapCase}
                    user={user}
                    onOpenDuplicate={onOpenDuplicate}
                    onClose={closeMapCase}
                    onOpen={() => {
                      setDetail(mapCase)
                      setMapCase(null)
                    }}
                  />
                )}
              </CaseMap>
              {mapData?.areas?.length > 0 && (
                <p className="text-xs text-muted">
                  Pins are cases whose location you may see. Numbered circles count the other cases
                  by village; exact locations stay with the district office and the claiming
                  organisation.
                </p>
              )}
            </div>
          ) : (
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
            {listError && <p role="alert" className="text-sm" style={{ color: 'var(--danger-600)' }}>{listError}</p>}
            {!loading && !listError && cases.length === 0 && (
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
                onOpen={openCase}
              />
            ))}
          </div>
          )}

          {detail && (
            <div className="stack vp-scroll" style={{ gap: 'var(--sp-12)', ...SCROLL_PANE }}>
              <ScorePanel
                detail={detail}
                user={user}
                onOpenDuplicate={onOpenDuplicate}
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
