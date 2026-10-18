import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import TwoFactorSettings from '../components/auth/TwoFactorSettings'

export default function Profile({ user, onSaved }) {
  useDocumentTitle('My profile')
  const [fullName, setFullName] = useState(user.full_name)
  const [phone, setPhone] = useState(user.phone || '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [errors, setErrors] = useState({})

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    setMessage(null)
    try {
      onSaved(await api.updateProfile({ full_name: fullName, phone }))
      setMessage('Saved.')
    } catch (err) {
      setErrors(err.fields || { detail: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>My profile</h1>
          <p>Keep your name and phone number up to date so the district office can reach you.</p>
        </div>
      </div>
      <form className="panel" onSubmit={submit} style={{ maxWidth: '48rem' }}>
        <div className="field">
          <label htmlFor="profile-email">Email</label>
          <input id="profile-email" className="input" value={user.email} disabled aria-describedby="profile-email-help" />
          <span id="profile-email-help" className="help">You sign in with this address, so it cannot be changed here.</span>
        </div>
        <div className="field">
          <label htmlFor="profile-name">Full name</label>
          <input id="profile-name" className="input" maxLength="100" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          {errors.full_name && <span role="alert" className="text-xs">{errors.full_name.join(' ')}</span>}
        </div>
        <div className="field">
          <label htmlFor="profile-phone">Phone</label>
          <input id="profile-phone" className="input" maxLength="20" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          {errors.phone && <span role="alert" className="text-xs">{errors.phone.join(' ')}</span>}
        </div>
        {errors.detail && <p role="alert" className="text-sm">{errors.detail}</p>}
        {message && <p role="status" className="text-sm">{message}</p>}
        <button className="btn btn--primary btn--sm" style={{ alignSelf: 'flex-start' }} disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>
      </form>
      <TwoFactorSettings />
    </>
  )
}
