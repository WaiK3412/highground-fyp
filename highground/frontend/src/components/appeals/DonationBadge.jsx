const BADGE = { waiting: 'badge--progress', received: 'badge--verified', cancelled: 'badge--resolved' }

export default function DonationBadge({ donation }) {
  return <span className={`badge ${BADGE[donation.status]}`}>{donation.status_display}</span>
}
