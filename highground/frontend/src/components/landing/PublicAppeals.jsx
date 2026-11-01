/** What relief organisations need right now, readable without signing in (ADR-025). */

import { api } from '../../api'
import { deadlineLabel } from '../../appeals'
import { formatDay } from '../../dates'
import ItemList from '../appeals/ItemList'
import { useLoad } from '../../useLoad'

export default function PublicAppeals({ onDonate }) {
  const { data: appeals, loading, error } = useLoad(
    () => api.publicAppeals().then((data) => data.results),
    [],
    [],
  )

  if (loading) return <p role="status" className="text-sm text-muted">Loading what is needed…</p>
  if (error) return <p className="text-sm text-muted">The list of needed supplies is not available right now.</p>
  if (appeals.length === 0)
    return <p className="text-sm text-muted" style={{ textAlign: 'center' }}>No organisation is asking for supplies right now.</p>

  return (
    <div className="grid-3">
      {appeals.map((appeal) => (
        <article key={appeal.id} className="card stack" style={{ gap: '0.8rem' }}>
          <h3 style={{ margin: 0 }}>{appeal.title}</h3>
          <p className="text-xs text-muted" style={{ margin: 0 }}>
            {appeal.organization} · needed until {formatDay(appeal.needed_until)} · {deadlineLabel(appeal.needed_until)}
          </p>
          <ItemList items={appeal.items} />
          <p className="text-sm" style={{ margin: 0 }}>
            <strong>Drop off at:</strong> {appeal.drop_off_point.name}, {appeal.drop_off_point.area}
          </p>
          <button className="btn btn--secondary btn--sm" style={{ alignSelf: 'flex-start', marginTop: '0.4rem' }} onClick={onDonate}>
            Log in to donate
          </button>
        </article>
      ))}
    </div>
  )
}
