export default function QueueSummary({ stats, unmet }) {
  return (
    <>
        {stats && (
          <div className="row" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
            <span className="map-kpi">
              <span className="map-kpi__value">{stats.total}</span> in this view
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value text-danger">
                {stats.health_critical}
              </span>{' '}
              health-critical
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value" style={{ color: 'var(--teal-700)' }}>
                {stats.unclaimed}
              </span>{' '}
              with help waiting
            </span>
            <span className="map-kpi">
              <span className="map-kpi__value">{stats.in_progress}</span> in progress
            </span>
          </div>
        )}

        {unmet && unmet.length > 0 && (
          <div className="banner banner--warning" role="status">
            <span className="body text-sm">
              <span className="title">Help no organisation has taken yet</span>
              <br />
              {unmet.map((row) => (
                <span key={row.help_type} className="block">
                  {row.help_type_display}: {row.open_jobs} {row.open_jobs === 1 ? 'job' : 'jobs'}
                  {row.health_critical > 0 ? `, ${row.health_critical} health-critical` : ''}, oldest
                  waiting {row.oldest_waiting_days} {row.oldest_waiting_days === 1 ? 'day' : 'days'}
                </span>
              ))}
            </span>
          </div>
        )}
    </>
  )
}
