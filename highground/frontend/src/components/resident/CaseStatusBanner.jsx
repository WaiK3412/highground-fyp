import { Icon, PATHS } from '../../icons'
import { CLOSED_STATUSES } from './caseStatus'

/**
 * ADR-012 §2 — where the role application stands. Only shown while there is
 * something to say: an ordinary resident who never applied sees nothing.
 */
export function ApplicationBanner({ user }) {
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

// Prioritise household actions in the banner because only the resident can complete them.
const NEEDS_RESIDENT = new Set(['needs_info', 'pending_confirm'])

/** Lead with household actions; otherwise show the oldest open case in the most urgent class. */
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

// Continue from the banner headline without repeating its status.
const BANNER_NEXT = {
  submitted: 'A district officer will review it and set its priority',
  needs_info: 'Open the case to see what the district office has asked for',
  verified: 'Waiting for a response team to take it on',
  claimed: 'They will schedule the work and keep you updated',
  in_progress: 'Someone will be in touch about access to your home',
  pending_confirm: 'Open the case and confirm the finished work',
}

export default function CaseStatusBanner({ cases, openCaseId = null, onOpen }) {
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
      {/* The banner names a case, so it should lead straight to it; hidden once it is open. */}
      {onOpen && openCaseId !== item.id && (
        <button
          type="button"
          className="btn btn--secondary btn--sm banner__action"
          onClick={() => onOpen(item.id)}
        >
          Open #{item.reference}
        </button>
      )}
    </div>
  )
}
