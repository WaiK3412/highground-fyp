import CaseTimeline from '../../pages/CaseTimeline'
import CaseFacts from '../CaseFacts'
import { STATUS_UI } from './caseStatus'
import CompletionDecision from './CompletionDecision'
import ReplyForm from './ReplyForm'

// Same tones as the case queue: class 1 "high", 2 "medium", 3 "low".
function priorityChipClass(priorityClass) {
  if (priorityClass === 1) return 'score score--high score--sm'
  if (priorityClass === 2) return 'score score--medium score--sm'
  return 'score score--low score--sm'
}

// Jobs exist from submission, but organisations can only claim them once the case is verified.
const NOT_YET_VERIFIED = new Set(['submitted', 'needs_info'])

/** FR10: show priority reasons to the household so it can understand its position in the queue. */
export default function CaseDetailPanel({ detail, onClose, onCompletionDecision, onReply, backButtonRef }) {
  const ui = STATUS_UI[detail.status] || STATUS_UI.submitted

  return (
    <aside className="stack meta-rail gap-24 resident-case-detail">
      <button ref={backButtonRef} type="button" className="btn btn--secondary resident-case-back" onClick={onClose}>
        ← Back to my cases
      </button>
      <div className="meta-rail__section">
        <div className="row--between" style={{ marginBottom: 'var(--sp-8)' }}>
          <div className="row" style={{ gap: 'var(--sp-8)' }}>
            <span className="text-strong case-reference" style={{ fontSize: 'var(--fs-20)' }}>
              #{detail.reference}
            </span>
            <span className={`badge ${ui.badge}`}>{detail.status_display}</span>
          </div>
          <button className="btn btn--ghost btn--sm resident-case-close" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="text-sm text-muted mb-12">
          {ui.next}
        </p>
        <p className="text-sm">{detail.description}</p>
      </div>

      {/* The office's question comes first: answering it is what moves the case on. */}
      {detail.status === 'needs_info' && <ReplyForm detail={detail} onReply={onReply} />}

      {detail.priority_class != null && (
        <div className="meta-rail__section" aria-label="Priority">
          <div className="card__header">
            <h2 className="h3">Why this priority</h2>
            <span
              className={priorityChipClass(detail.priority_class)}
              aria-label={`Priority class ${detail.priority_class}: ${detail.priority_label}`}
            >
              {detail.priority_class}
            </span>
          </div>
          <p className="text-strong priority-label">{detail.priority_label}</p>
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
          <h2 className="h3">Case details</h2>
        </div>
        <CaseFacts detail={detail}>
          <dt>Address</dt>
          <dd>{detail.location.address}</dd>
        </CaseFacts>
        <p className="text-xs text-muted" style={{ marginTop: 'var(--sp-12)' }}>
          {detail.location.precision === 'exact'
            ? 'Your full address is shown to you, and released only to the district office and the organisation that claims your case.'
            : 'Village-level only.'}
        </p>
      </div>

      {detail.tasks?.length > 0 && (
        <div className="meta-rail__section">
          <div className="card__header"><h2 className="h3">Recovery tasks</h2></div>
          <div className="stack gap-8">
            {detail.tasks.map((task) => (
              <div key={task.id} className="row--between gap-10">
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

      {/* ADR-020: confirm help types separately so one team cannot close another team's unfinished work. */}
      {(detail.jobs || []).length > 0 && (
        <div className="meta-rail__section" aria-label="Help on this request">
          <div className="card__header">
            <h2 className="h3">Help on this request</h2>
          </div>
          <ul className="text-sm" style={{ margin: 0, paddingLeft: '1.6rem' }}>
            {detail.jobs.map((job) => (
              <li key={job.id}>
                <strong>{job.help_type_display}</strong> —{' '}
                {NOT_YET_VERIFIED.has(detail.status)
                  ? 'opens to organisations once the district office verifies your request'
                  : job.status_display}
                {job.claimed_by ? ` · ${job.claimed_by}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(detail.jobs || []).filter((job) => ['pending_confirm', 'closed_unconfirmed'].includes(job.status)).map((job) => (
        <CompletionDecision key={job.id} job={job} photos={(detail.photos || []).filter((photo) => photo.job_id === job.id)} onDecision={onCompletionDecision} />
      ))}

      {/* Screen 06's timeline: every event_log row for this case, oldest first. */}
      <CaseTimeline events={detail.events} />
    </aside>
  )
}
