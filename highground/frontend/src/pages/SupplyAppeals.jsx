/** ADR-021: NGOs post needs/drop-off points; others read them, without pledging goods in the app. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import { useLoad } from '../useLoad'

const fmtDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })

function AppealCard({ appeal, canManage, onClose, onEdit, busy }) {
  return (
    <li className="card" style={{ listStyle: 'none', padding: 'var(--sp-16)' }}>
      <div className="row--between">
        <h3 style={{ margin: 0 }}>{appeal.title}</h3>
        <span className={`badge ${appeal.status === 'open' ? 'badge--verified' : 'badge--resolved'}`}>
          {appeal.status_display}
        </span>
      </div>
      <p className="text-sm text-muted" style={{ margin: '0.4rem 0 1rem' }}>
        {appeal.organization} · {appeal.organization_contact} · needed until {fmtDate(appeal.needed_until)}
      </p>
      <p className="text-sm" style={{ whiteSpace: 'pre-line' }}>{appeal.items}</p>
      <p className="text-sm" style={{ marginTop: '1rem' }}>
        <strong>Drop off at:</strong> {appeal.drop_off_point.name}, {appeal.drop_off_point.address} ({appeal.drop_off_point.area})
      </p>
      {canManage && appeal.status === 'open' && (
        <div className="row gap-8">
          <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => onEdit(appeal)}>Edit appeal</button>
          <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => onClose(appeal.id)}>
            {busy ? 'Closing…' : 'Close this appeal'}
          </button>
        </div>
      )}
    </li>
  )
}

function AppealForm({ appeal, onSaved, onCancel }) {
  const [points, setPoints] = useState([])
  const [form, setForm] = useState({ title: appeal?.title || '', items: appeal?.items || '', needed_until: appeal?.needed_until || '', drop_off_point_id: appeal?.drop_off_point.id || '' })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.dropOffPoints().then((data) => setPoints(data.results)).catch((err) => setErrors({ detail: err.message }))
  }, [])

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const payload = { ...form, drop_off_point_id: Number(form.drop_off_point_id) || null }
      onSaved(appeal ? await api.updateAppeal(appeal.id, payload) : await api.createAppeal(payload))
    } catch (err) {
      setErrors(err.fields || { detail: err.message })
    } finally {
      setBusy(false)
    }
  }

  const fieldError = (key) => errors[key] && (
    <span role="alert" className="text-xs text-danger">{[].concat(errors[key]).join(' ')}</span>
  )

  return (
    <form className="panel" onSubmit={submit} style={{ marginBottom: 'var(--sp-16)' }}>
      <div className="field">
        <label htmlFor="appeal-title">Title</label>
        <input id="appeal-title" className="input" maxLength="120" value={form.title} onChange={set('title')} required />
        {fieldError('title')}
      </div>
      <div className="field">
        <label htmlFor="appeal-items">Items needed</label>
        <textarea id="appeal-items" className="input" rows="4" maxLength="1000" value={form.items} onChange={set('items')} required />
        {fieldError('items')}
      </div>
      <div className="field">
        <label htmlFor="appeal-until">Needed until</label>
        <input id="appeal-until" type="date" className="input" value={form.needed_until} onChange={set('needed_until')} required />
        {fieldError('needed_until')}
      </div>
      <div className="field">
        <label htmlFor="appeal-point">Drop-off point</label>
        <select id="appeal-point" className="input" value={form.drop_off_point_id} onChange={set('drop_off_point_id')} required>
          <option value="">Choose a drop-off point</option>
          {points.map((point) => (
            <option key={point.id} value={point.id}>{point.name} — {point.area}</option>
          ))}
        </select>
        {fieldError('drop_off_point_id')}
      </div>
      {errors.detail && <p role="alert" className="text-sm">{errors.detail}</p>}
      <div className="row gap-8">
        <button className="btn btn--primary btn--sm" disabled={busy}>{busy ? 'Saving…' : appeal ? 'Save changes' : 'Post appeal'}</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

export default function SupplyAppeals({ user }) {
  useDocumentTitle(user.role === 'ngo_volunteer' ? 'Our supply appeals' : 'Supplies needed')
  const canManage = user.role === 'ngo_volunteer'
  const [actionError, setActionError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const { data: rows, setData: setRows, loading, error: loadError, reload } = useLoad(
    () => api.appeals(canManage ? { mine: '1' } : {}).then((data) => data.results),
    [canManage],
    [],
  )

  async function closeAppeal(id) {
    setBusyId(id)
    setActionError(null)
    try {
      const updated = await api.updateAppeal(id, { status: 'closed' })
      setRows((current) => current.map((row) => (row.id === id ? updated : row)))
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{canManage ? 'Our supply appeals' : 'Supplies needed'}</h1>
          <p className="text-sm text-muted">
            {canManage
              ? 'Tell the community what your organisation needs and where to bring it. Appeals disappear from the signed-in list after their date.'
              : 'Relief organisations are asking for these items. Take them to the drop-off point shown; you do not need to register anything here.'}
          </p>
        </div>
        {canManage && !showForm && (
          <button className="btn btn--primary" onClick={() => { setEditing(null); setShowForm(true) }}>New appeal</button>
        )}
      </div>

      {showForm && (
        <AppealForm
          key={editing?.id || 'new'}
          appeal={editing}
          onCancel={() => setShowForm(false)}
          onSaved={(appeal) => { setRows((current) => editing ? current.map((row) => row.id === appeal.id ? appeal : row) : [appeal, ...current]); setShowForm(false); setEditing(null) }}
        />
      )}

      {actionError && <p role="alert" className="text-sm">Could not update the appeal: {actionError}</p>}

      {loading ? (
        <p role="status" className="text-sm text-muted">Loading appeals…</p>
      ) : loadError ? (
        <p role="alert" className="text-sm">
          Could not load appeals: {loadError}{' '}
          <button className="btn btn--ghost btn--sm" onClick={reload}>Retry</button>
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">
          {canManage ? 'Your organisation has not posted an appeal yet.' : 'No organisation is asking for supplies right now.'}
        </p>
      ) : (
        <ul className="stack" style={{ gap: 'var(--sp-12)', padding: 0 }}>
          {rows.map((appeal) => (
            <AppealCard key={appeal.id} appeal={appeal} canManage={canManage} busy={busyId === appeal.id} onClose={closeAppeal} onEdit={(row) => { setEditing(row); setShowForm(true) }} />
          ))}
        </ul>
      )}
    </>
  )
}
