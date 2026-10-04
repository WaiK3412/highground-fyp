import { Icon, PATHS } from '../../icons'
import { STATUS_UI, CLOSED_STATUSES } from './caseStatus'

export default function CaseCard({ item, onOpen, isOpen }) {
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
