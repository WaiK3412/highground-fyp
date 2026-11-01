import { PriorityChip, JobChips, StatusBadge } from './CaseCard'
import { waitingText } from './caseHelpers'

/** Screen 10 keeps the map visible and uses the same role-filtered detail as the side panel. */
export default function MapCaseCard({ detail, user, onOpen, onClose, onOpenDuplicate }) {
  const canDecide = user.role === 'disaster_officer' && detail.status === 'submitted'
  const firstReason = detail.priority_reasons?.[0]
  return (
    <div className="ops-popover case-map__popover" role="dialog" aria-label={`Case ${detail.reference}`}>
      <div className="row--between" style={{ alignItems: 'flex-start' }}>
        <div>
          <div className="text-strong" style={{ fontSize: 'var(--fs-16)' }}>#{detail.reference}</div>
          <div className="text-xs text-muted">
            {detail.damage_category_display} · {detail.village}
          </div>
        </div>
        <PriorityChip item={detail} withLabel />
      </div>
      <div className="row wrap gap-8">
        <StatusBadge status={detail.status} label={detail.status_display} />
        {user.role === 'disaster_officer' && detail.has_open_duplicate && (
          <span className="badge badge--duplicate">Possible duplicate</span>
        )}
        {waitingText(detail) && <span className="text-xs text-muted">{waitingText(detail)}</span>}
      </div>
      <JobChips jobs={detail.jobs} caseStatus={detail.status} />
      <div className="text-xs text-muted">
        {detail.priority_class == null
          ? 'Not yet classified — classified when an officer verifies it.'
          : `${detail.priority_label}${firstReason ? ` — ${firstReason}` : ''}`}
      </div>
      <div className="text-xs text-muted">
        {detail.location.precision === 'exact'
          ? detail.location.address
          : 'Village-level location only'}
      </div>
      <div className="row gap-8">
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
