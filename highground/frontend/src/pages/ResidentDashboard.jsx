/**
 * Screen 04 — "My Recovery", the resident's home.
 *
 * A resident sees only their own household's cases; that narrowing happens on
 * the server in visible_cases(), not here, so this screen cannot leak another
 * household's case by forgetting a filter.
 *
 * It also carries the ADR-012 §2 state: an applicant waiting on a role
 * decision signs in as a resident and is told where the application stands,
 * rather than being locked out or left guessing.
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import CaseTimeline from './CaseTimeline'

// How each case status reads to the household that submitted it. The wording
// is deliberately about what happens next, not the internal status name.
// Task state is shown explicitly below, without inventing a numeric progress
// percentage. "Two of three tasks done" is auditable; "60% recovered" is not.
const STATUS_UI = {
  submitted: {
    badge: 'badge--new',
    next: 'Waiting for a district officer to review it',
  },
  needs_info: {
    badge: 'badge--escalated',
    next: 'The district office has asked for more information',
  },
  verified: {
    badge: 'badge--verified',
    next: 'Verified — waiting for a response team to take it on',
  },
  claimed: {
    badge: 'badge--assigned',
    next: 'A response team has taken this on',
  },
  in_progress: {
    badge: 'badge--progress',
    next: 'Work is under way',
  },
  pending_confirm: {
    badge: 'badge--progress',
    next: 'Waiting for you to confirm the work is finished',
  },
  closed: {
    badge: 'badge--resolved',
    next: 'Closed',
  },
  rejected: {
    badge: 'badge--escalated',
    next: 'Not accepted — open the case for the reason given',
  },
}

const CLOSED_STATUSES = new Set(['closed', 'rejected'])

// Slim, warm-toned scrollbars on the panels that scroll, plus a gutter so the
// cards are not pressed up against the bar. Set here rather than in styles.css:
// the design contract is frozen and never styles scrollbars, so this stays a
// code-level choice instead of a change to the design.
const SCROLL_PANE = {
  scrollbarWidth: 'thin',
  scrollbarColor: 'var(--grey-300) transparent',
  paddingRight: 'var(--sp-16)',
}

// `path` may be one string or several — Heroicons are single-path, Lucide's
// sprout is three.
function Icon({ path, strokeWidth = 1.5, style }) {
  const parts = Array.isArray(path) ? path : [path]
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth={strokeWidth} stroke="currentColor" style={style}>
      {parts.map((d, i) => (
        <path key={i} strokeLinecap="round" strokeLinejoin="round" d={d} />
      ))}
    </svg>
  )
}

const PATHS = {
  // Per damage category. All Heroicons outline — DESIGN-GUIDE.md:100 allows one
  // pack only, so these are chosen from what that pack has rather than from what
  // would be ideal. `sun` for agriculture is the weakest fit: Heroicons has no
  // crop, plant or field icon, and the card's label carries the meaning anyway.
  cleanup: 'M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z',
  repair: 'M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z',
  essential_items: 'm20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z',
  // The one exception to DESIGN-GUIDE.md's "never mix icon packs": Heroicons
  // has no crop, plant or field icon in all 316, and `sun` for Agriculture was
  // a stand-in. This is Lucide's `sprout` — same 24x24 grid and round caps, so
  // at strokeWidth 1.5 it sits at Heroicons' weight rather than Lucide's 2.
  agriculture: [
    'M14 9.536V7a4 4 0 0 1 4-4h1.5a.5.5 0 0 1 .5.5V5a4 4 0 0 1-4 4 4 4 0 0 0-4 4c0 2 1 3 1 5a5 5 0 0 1-1 3',
    'M4 9a5 5 0 0 1 8 4 5 5 0 0 1-8-4',
    'M5 21h14',
  ],
  other: 'M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  home: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75',
  plus: 'M12 4.5v15m7.5-7.5h-15',
  folder:
    'M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z',
  bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0',
  heart: 'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z',
  user: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  logo: 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0',
  warning:
    'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
}

/**
 * ADR-012 §2 — where the role application stands. Only shown while there is
 * something to say: an ordinary resident who never applied sees nothing.
 */
function ApplicationBanner({ user }) {
  if (user.verification_status === 'pending') {
    return (
      <div className="banner banner--info">
        <Icon path={PATHS.bell} />
        <span className="body">
          <span className="title">
            Your application to join as{' '}
            {user.requested_role === 'ngo_volunteer'
              ? 'an NGO responder'
              : `a ${(user.requested_role_display || '').toLowerCase()}`}{' '}
            is under review.
          </span>
          <br />
          Until it is approved, this works as an ordinary resident account.
        </span>
      </div>
    )
  }

  if (user.verification_status === 'rejected') {
    return (
      <div className="banner banner--warning">
        <Icon path={PATHS.bell} />
        <span className="body">
          <span className="title">Your role application was not approved.</span>
          <br />
          {user.verification_note || 'No reason was recorded.'} Your resident account
          is unaffected.
        </span>
      </div>
    )
  }

  return null
}

// Same tones as the case queue: class 1 "high", 2 "medium", 3 "low".
function priorityChipClass(priorityClass) {
  if (priorityClass === 1) return 'score score--high score--sm'
  if (priorityClass === 2) return 'score score--medium score--sm'
  return 'score score--low score--sm'
}

// "child_under_5" reads badly to the household it describes.
const humanise = (flag) => flag.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())


function CompletionDecision({ job, onDecision }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function decide(decision) {
    setBusy(true)
    setError(null)
    try {
      await onDecision(job.id, decision, note)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="meta-rail__section">
      <div className="banner banner--warning">
        <span className="body">
          <span className="title">Is the {job.help_type_display.toLowerCase()} work by {job.claimed_by} complete?</span>
          <br />
          Confirm only after checking the work. If something remains, explain it so the response
          team has a clear follow-up record.
        </span>
      </div>
      <div className="field" style={{ marginTop: '1.2rem' }}>
        <label htmlFor={`completion-note-${job.id}`}>What still needs attention? (required if incomplete)</label>
        <textarea
          id={`completion-note-${job.id}`}
          className="input"
          rows="3"
          maxLength="1000"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      <div className="row" style={{ gap: '0.8rem', marginTop: '1rem', flexWrap: 'wrap' }}>
        <button className="btn btn--primary btn--sm" disabled={busy} onClick={() => decide('confirm')}>
          Confirm complete
        </button>
        <button
          className="btn btn--ghost btn--sm"
          disabled={busy || !note.trim()}
          onClick={() => decide('incomplete')}
        >
          Report incomplete work
        </button>
      </div>
      {error && <p role="alert" className="text-xs" style={{ color: 'var(--danger-600)', marginTop: '0.8rem' }}>{error}</p>}
    </div>
  )
}

/**
 * The resident's own case, opened from a card.
 *
 * The point of this panel is the priority and its reasons (FR10).
 * Explainability exists for the household being prioritised, not only for the
 * officer — someone told their case is Standard is owed the reasoning.
 */
function CaseDetailPanel({ detail, onClose, onCompletionDecision }) {
  const ui = STATUS_UI[detail.status] || STATUS_UI.submitted
  const list = (flags) => (flags?.length ? flags.map(humanise).join(' · ') : '—')

  return (
    <aside className="stack meta-rail" style={{ gap: '2.4rem' }}>
      <div className="meta-rail__section">
        <div className="row--between" style={{ marginBottom: 'var(--sp-8)' }}>
          <div className="row" style={{ gap: 'var(--sp-8)' }}>
            <span className="text-strong" style={{ fontSize: 'var(--fs-20)' }}>
              #{detail.reference}
            </span>
            <span className={`badge ${ui.badge}`}>{detail.status_display}</span>
          </div>
          <button className="btn btn--ghost btn--sm" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="text-sm text-muted" style={{ marginBottom: 'var(--sp-12)' }}>
          {ui.next}
        </p>
        <p className="text-sm">{detail.description}</p>
      </div>

      {detail.priority_class != null && (
        <div className="meta-rail__section" aria-label="Priority">
          <div className="card__header">
            <h3>Why this priority</h3>
            <span
              className={priorityChipClass(detail.priority_class)}
              aria-label={`Priority class ${detail.priority_class}: ${detail.priority_label}`}
            >
              {detail.priority_class}
            </span>
          </div>
          <p className="text-strong">{detail.priority_label}</p>
          <ul className="text-sm" style={{ margin: 'var(--sp-8) 0 0', paddingLeft: '1.6rem' }}>
            {(detail.priority_reasons || []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <hr className="divider" style={{ margin: '1.2rem 0' }} />
          <span className="text-sm text-muted">
            Requests are served by priority class, then in the order they were submitted
            (classes-1.0), and checked by district officers.
          </span>
        </div>
      )}

      <div className="meta-rail__section">
        <div className="card__header">
          <h3>Case details</h3>
        </div>
        <dl className="kv">
          <dt>Case ID</dt>
          <dd>#{detail.reference}</dd>
          <dt>Type</dt>
          <dd>{detail.damage_category_display}</dd>
          <dt>Flood depth</dt>
          <dd>{detail.flood_depth_display}</dd>
          <dt>Home liveable</dt>
          <dd>{detail.liveability_display}</dd>
          <dt>Urgency</dt>
          <dd>{detail.urgency_display}</dd>
          <dt>Access</dt>
          <dd>{detail.access_level_display}</dd>
          <dt>Household</dt>
          <dd>
            {detail.household_size} {detail.household_size === 1 ? 'member' : 'members'}
            {detail.vulnerability_flags?.length > 0 &&
              ` · ${list(detail.vulnerability_flags)}`}
          </dd>
          <dt>Essential needs</dt>
          <dd>{list(detail.needs_flags)}</dd>
          <dt>Address</dt>
          <dd>{detail.location.address}</dd>
        </dl>
        <p className="text-xs text-muted" style={{ marginTop: 'var(--sp-12)' }}>
          {detail.location.precision === 'exact'
            ? 'Your full address is shown to you, and released only to the district office and the organisation that claims your case.'
            : 'Village-level only.'}
        </p>
      </div>

      {detail.tasks?.length > 0 && (
        <div className="meta-rail__section">
          <div className="card__header"><h3>Recovery tasks</h3></div>
          <div className="stack" style={{ gap: '0.8rem' }}>
            {detail.tasks.map((task) => (
              <div key={task.id} className="row--between" style={{ gap: '1rem' }}>
                <div>
                  <div className="text-sm text-strong">{task.title}</div>
                  <div className="text-xs text-muted">
                    {task.task_type_display} · {task.lead_name || 'Responder not assigned yet'}
                  </div>
                </div>
                <span className="badge badge--assigned">{task.status_display}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Each type of help is confirmed separately: one organisation finishing
          never closes help another still owes (ADR-020). */}
      {(detail.jobs || []).length > 0 && (
        <div className="meta-rail__section" aria-label="Help on this request">
          <div className="card__header">
            <h3>Help on this request</h3>
          </div>
          <ul className="text-sm" style={{ margin: 0, paddingLeft: '1.6rem' }}>
            {detail.jobs.map((job) => (
              <li key={job.id}>
                <strong>{job.help_type_display}</strong> — {job.status_display}
                {job.claimed_by ? ` · ${job.claimed_by}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(detail.jobs || []).filter((job) => job.status === 'pending_confirm').map((job) => (
        <CompletionDecision key={job.id} job={job} onDecision={onCompletionDecision} />
      ))}

      {/* Screen 06's timeline: every event_log row for this case, oldest first. */}
      <CaseTimeline events={detail.events} />
    </aside>
  )
}

// Statuses where the case is waiting on the household rather than on a
// responder. These come first in the banner because they are the only ones the
// resident can actually act on.
const NEEDS_RESIDENT = new Set(['needs_info', 'pending_confirm'])

/**
 * The one case worth leading with.
 *
 * Anything waiting on the household outranks everything else; among the rest,
 * the highest-scoring open case. Counting cases told a household nothing they
 * could not already see in the list — this says what is happening and whether
 * they need to do something.
 */
function focusCase(cases) {
  const open = cases.filter((item) => !CLOSED_STATUSES.has(item.status))
  if (open.length === 0) return null

  const waitingOnThem = open.filter((item) => NEEDS_RESIDENT.has(item.status))
  const pool = waitingOnThem.length > 0 ? waitingOnThem : open

  // Most urgent class first (1 beats 3; unclassified last), then the oldest.
  const rank = (item) => item.priority_class ?? 99
  return pool.reduce((best, item) => {
    if (rank(item) !== rank(best)) return rank(item) < rank(best) ? item : best
    return new Date(item.created_at) < new Date(best.created_at) ? item : best
  })
}

// The card's "next" line restates the status, which reads as a repetition once
// the banner headline has already said it. These carry on from the headline
// instead, and say what the household should expect or do.
const BANNER_NEXT = {
  submitted: 'A district officer will review it and set its priority',
  needs_info: 'Open the case to see what the district office has asked for',
  verified: 'Waiting for a response team to take it on',
  claimed: 'They will schedule the work and keep you updated',
  in_progress: 'Someone will be in touch about access to your home',
  pending_confirm: 'Open the case and confirm the finished work',
}

function CaseStatusBanner({ cases }) {
  const item = focusCase(cases)
  if (!item) return null

  const headline = {
    submitted: `#${item.reference} has been received`,
    needs_info: `#${item.reference} needs more information from you`,
    verified: `#${item.reference} has been verified and prioritised`,
    claimed: `${(item.jobs || []).filter((job) => job.claimed_by).map((job) => job.claimed_by).join(' and ') || 'A response team'} has taken on #${item.reference}`,
    in_progress: `Work has started on #${item.reference}`,
    pending_confirm: `Confirm the work on #${item.reference} is finished`,
  }[item.status]

  const waited =
    item.days_waiting === 0
      ? 'submitted today'
      : `${item.days_waiting} ${item.days_waiting === 1 ? 'day' : 'days'} so far`

  const actionable = NEEDS_RESIDENT.has(item.status)

  return (
    <div className={`banner ${actionable ? 'banner--warning' : 'banner--info'}`}>
      <Icon path={actionable ? PATHS.warning : PATHS.bell} />
      <span className="body">
        <span className="title">{headline}</span>
        <br />
        {item.priority_class != null && (
          <>
            Priority class {item.priority_class} ({item.priority_label}).{' '}
          </>
        )}
        {BANNER_NEXT[item.status]} · {waited}.
      </span>
    </div>
  )
}

function CaseCard({ item, onOpen, isOpen }) {
  const ui = STATUS_UI[item.status] || STATUS_UI.submitted
  const settled = CLOSED_STATUSES.has(item.status)

  return (
    <button
      type="button"
      className="card card--flat"
      onClick={() => onOpen(item.id)}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        font: 'inherit',
        cursor: 'pointer',
        opacity: settled ? 0.75 : 1,
        outline: isOpen ? '2px solid var(--teal-700)' : undefined,
      }}
    >
      <div className="row--between" style={{ marginBottom: '1.2rem' }}>
        <div className="row">
          <span
            className={`stat-card__icon ${settled ? 'icon-bg--success' : 'icon-bg--info'}`}
            style={{ width: '3.6rem', height: '3.6rem' }}
          >
            <Icon path={PATHS[item.damage_category] || PATHS.other} style={{ width: '1.8rem', height: '1.8rem' }} />
          </span>
          <div>
            <div className="text-strong">{item.damage_category_display}</div>
            <div className="text-xs text-muted">
              #{item.reference} · {item.village} ·{' '}
              {item.days_waiting === 0
                ? 'submitted today'
                : `submitted ${item.days_waiting} ${item.days_waiting === 1 ? 'day' : 'days'} ago`}
            </div>
          </div>
        </div>
        <span className={`badge ${ui.badge}`}>{item.status_display}</span>
      </div>

      <div className="row--between" style={{ marginBottom: '0.6rem' }}>
        <span className="text-xs text-muted">{ui.next}</span>
        {item.priority_class != null && (
          <span className="text-xs text-strong">
            Priority {item.priority_label}
          </span>
        )}
      </div>
    </button>
  )
}

export default function ResidentDashboard({ user, onLogout, onSubmitRequest, onNavigate }) {
  useDocumentTitle('My Recovery')
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [detail, setDetail] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [detailLoadingId, setDetailLoadingId] = useState(null)
  const detailVersion = useRef(0)
  const [unread, setUnread] = useState(0)

  // The list carries only summary fields; the breakdown, needs and location
  // come from the detail endpoint, which applies its own visibility rules.
  async function openCase(id) {
    const version = ++detailVersion.current
    setDetailError(null)
    if (detail?.id === id) {
      setDetail(null)
      return
    }
    setDetail(null)
    setDetailLoadingId(id)
    try {
      const result = await api.caseDetail(id)
      if (version === detailVersion.current) setDetail(result)
    } catch (err) {
      if (version === detailVersion.current) setDetailError({ message: err.message, id })
    } finally {
      if (version === detailVersion.current) setDetailLoadingId(null)
    }
  }

  async function decideCompletion(jobId, decision, note) {
    await api.confirmJob(jobId, decision, note)
    const [updatedDetail, updatedCases] = await Promise.all([
      api.caseDetail(detail.id),
      api.cases(),
    ])
    setDetail(updatedDetail)
    setCases(updatedCases.results)
  }

  useEffect(() => {
    api
      .notifications()
      .then((data) => setUnread(data.unread))
      .catch(() => setUnread(0))
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .cases()
      .then((list) => !cancelled && setCases(list.results))
      .catch((err) => !cancelled && setLoadError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [loadAttempt])

  const firstName = user.full_name.split(' ')[0]
  const initials = user.full_name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#recovery" onClick={(e) => e.preventDefault()}>
          <span className="logo__mark">
            <Icon path={PATHS.logo} strokeWidth={2} />
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">Resident</span>
          </span>
        </a>

        <nav className="side-nav">
          {/* "My Recovery", not "Dashboard" — the word the design contract uses
              in this screen's own title. A household is not monitoring a system,
              and report §2.2.4 argues for the user's vocabulary in a crisis
              context. The responder screens keep operational language. */}
          <a href="#recovery" className="active" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.home} />
            My Recovery
          </a>
          <a
            href="#submit"
            onClick={(e) => {
              e.preventDefault()
              onSubmitRequest()
            }}
          >
            <Icon path={PATHS.plus} />
            Submit a request
          </a>
          <a href="#cases" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.folder} />
            My cases
            {cases.length > 0 && <span className="side-nav__count">{cases.length}</span>}
          </a>
          <a
            href="#notifications"
            onClick={(e) => {
              e.preventDefault()
              onNavigate('notifications')
            }}
          >
            <Icon path={PATHS.bell} />
            Notifications
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>

          <span className="side-nav__label">Community</span>
          <span className="side-nav__item side-nav__item--soon" aria-disabled="true">
            <Icon path={PATHS.heart} />
            Pledge supplies <span className="side-nav__soon-tag">Coming soon</span>
          </span>

          <span className="side-nav__label">Account</span>
          <a href="#profile" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.user} />
            My profile
          </a>
        </nav>

        <div className="sidebar__user">
          <span className="avatar">{initials}</span>
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
            <h1>Selamat datang, {firstName} </h1>
            <p>Here is the latest on your household&apos;s recovery.</p>
          </div>
          <button className="btn btn--primary" onClick={onSubmitRequest}>
            <Icon path={PATHS.plus} strokeWidth={2} />
            Submit a request
          </button>
        </div>

        <div className="stack" style={{ gap: 'var(--sp-12)', marginBottom: '1.6rem' }}>
          <ApplicationBanner user={user} />
          {!loading && <CaseStatusBanner cases={cases} />}
        </div>

        {/* vp-fill takes the remaining viewport height and each column scrolls
            inside itself, so a long detail panel never leaves a tall empty
            column beside it. The header and banners stay pinned. */}
        <div
          className="grid-2 vp-fill"
          style={{
            gridTemplateColumns: detail ? '1.5fr 1fr' : '1fr',
            gap: '1.6rem',
          }}
        >
          <div className="stack vp-scroll" style={{ gap: '1.6rem', ...SCROLL_PANE }}>
          <div className="card">
            <div className="card__header">
              <h3>My cases</h3>
              {cases.length > 0 && (
                <span className="text-xs text-muted">Select a case to see its detail</span>
              )}
            </div>

            {detailError && (
              <div
                role="alert"
                className="text-sm"
                style={{ color: 'var(--danger-600)', fontWeight: 600, marginBottom: '1.2rem' }}
              >
                {detailError.message} <button className="btn btn--ghost btn--sm" onClick={() => openCase(detailError.id)}>Retry</button>
              </div>
            )}
            {detailLoadingId && <p role="status" className="text-sm text-muted">Loading case detail…</p>}

            {loading ? (
              <p className="text-sm text-muted">Loading your cases…</p>
            ) : loadError ? (
              <p role="alert" className="text-sm">Could not load your cases. <button className="btn btn--ghost btn--sm" onClick={() => { setLoadError(null); setLoading(true); setLoadAttempt((n) => n + 1) }}>Retry</button></p>
            ) : cases.length === 0 ? (
              <p className="text-sm text-muted">
                You have not submitted a request yet. When you do, it will appear here with its
                priority and progress.
              </p>
            ) : (
              <div className="stack" style={{ gap: '1.6rem' }}>
                {cases.map((item) => (
                  <CaseCard
                    key={item.id}
                    item={item}
                    onOpen={openCase}
                    isOpen={detail?.id === item.id}
                  />
                ))}
              </div>
            )}
          </div>

            <div className="card" style={{ background: 'var(--sand-100)' }}>
              <div className="row--between" style={{ gap: '1.6rem', flexWrap: 'wrap' }}>
                <div>
                  <h3 style={{ marginBottom: '0.4rem' }}>
                    Not affected this season? Your neighbours could use a hand.
                  </h3>
                  <p className="text-sm text-muted">
                    Pledge cleaning kits, bedding or water to a drop-off point. Goods only,
                    never money.
                  </p>
                </div>
                <span className="badge badge--new">Coming soon</span>
              </div>
            </div>
          </div>

          {detail && (
            <div className="stack vp-scroll" style={{ gap: '1.6rem', ...SCROLL_PANE }}>
              <CaseDetailPanel
                detail={detail}
                onClose={() => setDetail(null)}
                onCompletionDecision={decideCompletion}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
