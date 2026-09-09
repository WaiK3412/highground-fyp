/**
 * Screen 06 — case tracking, the timeline half.
 *
 * Rendered inside the resident's case detail. Every entry is a case_event_log
 * row (ADR-004), which is why the same records serve this, the notifications
 * list and the audit trail. The API returns canonical actions only (not extra
 * per-recipient notification rows) and withholds internal note text from a
 * resident while retaining the public event in the history.
 */

const TICK = 'M4.5 12.75l6 6 9-13.5'

// Plain-language titles. The stored event_display is operational wording
// ("Needs info requested"); a household reading about their own home deserves
// the sentence, not the status name.
const TITLES = {
  submitted: 'Request received',
  needs_info: 'More information requested',
  verified: 'Verified & prioritised by the district disaster office',
  rejected: 'Not accepted',
  score_computed: 'Priority score computed',
  claimed: 'An organisation took on your case',
  task_assigned: 'A team was assigned',
  task_updated: 'Work updated',
  escalated: 'Escalated for a decision',
  closed: 'Case closed',
  reopened: 'Case reopened',
  score_overridden: 'Priority score adjusted by an officer',
}

function when(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    + ' · ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export default function CaseTimeline({ events = [] }) {
  if (events.length === 0) return null

  return (
    <div className="meta-rail__section">
      <div className="card__header">Case history</div>
      <div className="timeline">
        {events.map((event, index) => (
          <div className="timeline__item" key={`${event.created_at}-${index}`}>
            <div className="timeline__dot timeline__dot--done">
              <svg fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d={TICK} />
              </svg>
            </div>
            <div className="timeline__body">
              <div className="title">{TITLES[event.event_type] || event.event_display}</div>
              <div className="meta">
                {when(event.created_at)}
                {event.actor_org
                  ? ` · ${event.actor_org}`
                  : event.actor
                    ? ` · ${event.actor}`
                    : ''}
              </div>
              {/* Deliberately household-visible wording, where the API supplies it. */}
              {event.detail && <div className="note">{event.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
