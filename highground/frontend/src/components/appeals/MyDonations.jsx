/** A resident's own donations, newest first, with Cancel while still waiting. */

import { api } from '../../api'
import { formatDay } from '../../dates'
import { useRowAction } from '../../useRowAction'
import DonationBadge from './DonationBadge'

export default function MyDonations({ donations, setDonations }) {
  const { busyId, error, run } = useRowAction(setDonations)
  if (donations.length === 0) return null

  return (
    <section className="panel" style={{ marginBottom: 'var(--sp-16)' }}>
      <h2 className="panel-title" style={{ marginBottom: 'var(--sp-12)' }}>My donations</h2>
      {error && <p role="alert" className="text-sm">Could not cancel the donation: {error}</p>}
      <ul className="stack" style={{ gap: 'var(--sp-12)', padding: 0, margin: 0 }}>
        {donations.map((donation) => (
          <li key={donation.id} className="row--between" style={{ listStyle: 'none', gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
            <div>
              <strong>{donation.appeal.title}</strong>
              <div className="text-sm">{donation.items}</div>
              <div className="text-xs text-muted">
                Drop off at {donation.appeal.drop_off_point} · recorded {formatDay(donation.created_at)}
                {donation.received_at && ` · received ${formatDay(donation.received_at)}`}
              </div>
            </div>
            <div className="row gap-8">
              <DonationBadge donation={donation} />
              {donation.status === 'waiting' && (
                <button
                  className="btn btn--ghost btn--sm"
                  disabled={busyId !== null}
                  onClick={() => run(donation.id, () => api.cancelDonation(donation.id))}
                >
                  {busyId === donation.id ? 'Cancelling…' : 'Cancel'}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
