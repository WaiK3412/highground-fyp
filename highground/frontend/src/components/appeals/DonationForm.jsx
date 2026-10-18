/** A resident says what they will bring to one appeal (ADR-025). */

import { useState } from 'react'
import { api } from '../../api'

export default function DonationForm({ appeal, onDonated, onCancel }) {
  const [items, setItems] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const fieldId = `donation-items-${appeal.id}`

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDonated(await api.donate(appeal.id, items))
    } catch (err) {
      setError(err.fields?.items?.join(' ') || err.message)
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: 'var(--sp-12)', marginTop: '1rem' }} onSubmit={submit}>
      <div className="field">
        <label htmlFor={fieldId}>What are you bringing?</label>
        <textarea
          id={fieldId}
          className="input"
          rows="3"
          maxLength="500"
          value={items}
          onChange={(event) => setItems(event.target.value)}
          placeholder="For example: 10 kg rice, 2 boxes of drinking water"
          required
        />
        <span className="help">{appeal.organization} will see your name and phone number so they can reach you.</span>
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="row gap-8">
        <button className="btn btn--primary btn--sm" disabled={busy}>{busy ? 'Saving…' : 'Record donation'}</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
