import { openJobsFor, confirmationDays, waitingText } from './caseHelpers'
import { STATUS_UI } from '../resident/caseStatus'

// The same status colours the household sees, so "Needs info" never looks like "Verified".
export function StatusBadge({ status, label }) {
  return <span className={`badge ${STATUS_UI[status]?.badge || 'badge--new'}`}>{label}</span>
}

// One line per type of help: who holds it, or that it is still waiting.
export function JobChips({ jobs, caseStatus }) {
  // A rejected request's help will never be claimed, so "waiting" would mislead.
  if (caseStatus === 'rejected') return null
  return (
    <div className="row" style={{ flexWrap: 'wrap', gap: '0.6rem' }}>
      {(jobs || []).map((job) => (
        <span key={job.id} className="filter-chip" title={job.status_display}>
          {job.help_type_display} ·{' '}
          {job.claimed_by ? (job.claimed_by_you ? 'your organisation' : job.claimed_by) : 'waiting'}
          {job.status === 'done' ? ' · done' : ''}
          {job.status === 'closed_unconfirmed' ? ' · closed without household confirmation' : ''}
        </span>
      ))}
    </div>
  )
}

// Class 1 uses the "high" tone, 2 "medium", 3 "low"; unclassified is neutral.
function priorityChipClass(priorityClass) {
  if (priorityClass === 1) return 'score score--high score--sm'
  if (priorityClass === 2) return 'score score--medium score--sm'
  if (priorityClass === 3) return 'score score--low score--sm'
  return 'score score--neutral score--sm'
}

export function PriorityChip({ item, withLabel = false }) {
  const chip = (
    <span
      className={priorityChipClass(item.priority_class)}
      title={item.priority_label || 'Not yet classified'}
      aria-label={
        item.priority_class
          ? `Priority class ${item.priority_class}: ${item.priority_label}`
          : 'Not yet classified'
      }
    >
      {item.priority_class ?? '—'}
    </span>
  )
  if (!withLabel) return chip
  // The label beside the number, so the class is readable without hovering.
  return (
    <span className="priority-tag">
      <span className="priority-tag__label" aria-hidden="true">{item.priority_label || 'Not yet classified'}</span>
      {chip}
    </span>
  )
}

export default function CaseCard({ item, onOpen, onClaim, selected, user, busy }) {
  // Screen 07 shows a claim button on the card for each type of help still waiting.
  const openJobs = openJobsFor(user, item)
  const canClaim = openJobs.length > 0
  const canDecide = user.role === 'disaster_officer' && item.status === 'submitted'

  return (
    <div className={`ops-card${selected ? ' ops-card--selected' : ''}`}>
      <div className="row--between">
        <span className="title">#{item.reference}</span>
        <PriorityChip item={item} withLabel />
      </div>
      <span className="meta">
        {[item.damage_category_display, item.village, `household of ${item.household_size}`, waitingText(item)]
          .filter(Boolean)
          .join(' · ')}
      </span>
      <div className="row wrap gap-8">
        <StatusBadge status={item.status} label={item.status_display} />
        {user.role === 'disaster_officer' && item.has_open_duplicate && (
          <span className="badge badge--duplicate">Possible duplicate</span>
        )}
        {item.reported_urgent && (
          <span className="badge badge--escalated">Reported urgent · not yet verified</span>
        )}
        {user.role === 'disaster_officer' && item.awaiting_confirmation_since && (
          <span className="badge badge--new">
            Waiting for household · {confirmationDays(item.awaiting_confirmation_since)} days
          </span>
        )}
      </div>
      <JobChips jobs={item.jobs} caseStatus={item.status} />
      <div className="row wrap gap-8">
        {openJobs.map((job) => (
          <button
            key={job.id}
            className="btn btn--primary btn--sm"
            disabled={busy}
            onClick={() => onClaim(job.id)}
          >
            {busy ? 'Claiming…' : `Claim ${job.help_type_display.toLowerCase()}`}
          </button>
        ))}
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
