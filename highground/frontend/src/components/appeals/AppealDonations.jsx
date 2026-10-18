/** The donations recorded for one of this NGO's appeals, with "Mark received". */

import { useState } from 'react'
import { api } from '../../api'
import { formatDay } from '../../dates'
import { useLoad } from '../../useLoad'
import { useRowAction } from '../../useRowAction'
import DonationBadge from './DonationBadge'

export default function AppealDonations({ appeal }) {
  const [open, setOpen] = useState(false)
  const { data: donations, setData: setDonations, loading, error: loadError, reload } = useLoad(
    () => api.appealDonations(appeal.id).then((data) => data.results),
    [appeal.id],
    [],
  )
  const { busyId, error, run } = useRowAction(setDonations)
  const waiting = donations.filter((donation) => donation.status === 'waiting').length

  return (
    <div style={{ marginTop: '1rem' }}>
      <button className="btn btn--ghost btn--sm" aria-expanded={open} onClick={() => setOpen(!open)}>
        {loading ? 'Donations…' : `Donations: ${waiting} waiting for drop-off`}
      </button>
      {open && (
        <div className="stack" style={{ gap: 'var(--sp-12)', marginTop: 'var(--sp-12)' }}>
          {loadError && (
            <p role="alert" className="text-sm">
              Could not load donations: {loadError}{' '}
              <button className="btn btn--ghost btn--sm" onClick={reload}>Retry</button>
            </p>
          )}
          {error && <p role="alert" className="text-sm">Could not mark it received: {error}</p>}
          {!loading && donations.length === 0 && <p className="text-sm text-muted">No donations recorded yet.</p>}
          {donations.map((donation) => (
            <div key={donation.id} className="row--between" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
              <div>
                <strong>{donation.donor_name}</strong> · {donation.donor_phone}
                <div className="text-sm">{donation.items}</div>
                <div className="text-xs text-muted">
                  Recorded {formatDay(donation.created_at)}
                  {donation.received_by && ` · received by ${donation.received_by} on ${formatDay(donation.received_at)}`}
                </div>
              </div>
              <div className="row gap-8">
                <DonationBadge donation={donation} />
                {donation.status === 'waiting' && (
                  <button
                    className="btn btn--primary btn--sm"
                    disabled={busyId !== null}
                    onClick={() => run(donation.id, () => api.receiveDonation(donation.id))}
                  >
                    {busyId === donation.id ? 'Saving…' : 'Mark received'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
