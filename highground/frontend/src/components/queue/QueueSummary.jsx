import { useState } from 'react'

// The overview row (FR13, FR16): counts over the whole queue this user may see.
// Each count opens the matching list, so a number is always one click from its cases.
const HEALTH_CRITICAL = { key: 'health_critical', label: 'health-critical', tone: 'text-danger', filter: { priority: '1' } }
const AWAITING_HOUSEHOLD = { key: 'awaiting_household', label: 'awaiting the household', filter: { status: 'pending_confirm' } }
const COUNTS = {
  disaster_officer: [
    { key: 'to_verify', label: 'to verify', filter: { status: 'submitted' } },
    HEALTH_CRITICAL,
    { key: 'help_waiting', label: 'with help no one has taken', filter: { scope: 'open_help' } },
    AWAITING_HOUSEHOLD,
  ],
  ngo_volunteer: [
    { key: 'help_waiting', label: 'with help to claim', filter: { scope: 'open_help' } },
    { key: 'ours', label: 'held by your organisation', filter: { scope: 'mine' } },
    AWAITING_HOUSEHOLD,
    HEALTH_CRITICAL,
  ],
}

function isActive(filter, current) {
  return Object.entries(filter).every(([name, value]) => current[name] === value)
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`
}

export default function QueueSummary({ user, overview, unmet, current, apply }) {
  const [byTypeOpen, setByTypeOpen] = useState(false)
  if (!overview) return null
  const oldest = unmet?.length ? Math.max(...unmet.map((row) => row.oldest_waiting_days)) : null

  return (
    <div className="queue-overview">
      <div className="queue-overview__counts" role="group" aria-label="Queue overview">
        {(COUNTS[user.role] || []).map((count) => {
          const active = isActive(count.filter, current)
          return (
            <button
              key={count.key}
              type="button"
              className={`queue-stat${active ? ' queue-stat--active' : ''}`}
              aria-pressed={active}
              title={active ? 'Show the whole queue' : 'Show these cases'}
              onClick={() => apply(active ? {} : count.filter)}
            >
              <span className={`queue-stat__value ${count.tone || ''}`}>{overview[count.key] ?? 0}</span>
              {count.label}
              {count.key === 'help_waiting' && oldest !== null && (
                <span className="queue-stat__note">oldest {plural(oldest, 'day', 'days')}</span>
              )}
            </button>
          )
        })}
        {unmet?.length > 0 && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            aria-expanded={byTypeOpen}
            aria-controls="queue-unmet"
            onClick={() => setByTypeOpen((open) => !open)}
          >
            {byTypeOpen ? 'Hide' : 'Untaken help'} by type
          </button>
        )}
      </div>
      {unmet?.length > 0 && byTypeOpen && (
        <ul id="queue-unmet" className="queue-overview__unmet" aria-label="Help no organisation has taken yet, by type">
          {unmet.map((row) => (
            <li key={row.help_type}>
              <button type="button" className="link-button" onClick={() => apply({ help: row.help_type })}>
                {row.help_type_display}
              </button>
              : {plural(row.open_jobs, 'job', 'jobs')}
              {row.health_critical > 0 ? `, ${row.health_critical} health-critical` : ''}, oldest waiting{' '}
              {plural(row.oldest_waiting_days, 'day', 'days')}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
