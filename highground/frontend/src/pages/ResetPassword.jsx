/** Choose a new password from an emailed link (/reset-password/<uid>/<token>). */

import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import AuthAlert from '../components/auth/AuthAlert'
import AuthLayout, { AuthLinkButton } from '../components/auth/AuthLayout'

export default function ResetPassword({ uid, token, onDone, onRequestNewLink, onShowLogin }) {
  useDocumentTitle('Choose a new password')
  const [passwords, setPasswords] = useState({ first: '', second: '' })
  const [error, setError] = useState(null)
  const [linkInvalid, setLinkInvalid] = useState(false)
  const [busy, setBusy] = useState(false)

  const set = (key) => (event) => setPasswords({ ...passwords, [key]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.primeCsrf()
      const result = await api.confirmPasswordReset(uid, token, passwords.first, passwords.second)
      onDone(result.detail)
    } catch (err) {
      setLinkInvalid(err.code === 'invalid_link')
      // Django puts both "too weak" and "do not match" under the second field.
      setError(err.fields ? Object.values(err.fields).flat().join(' ') : err.message)
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="Use at least 8 characters that are not easy to guess.">
      <div className="auth-card">
        {linkInvalid ? (
          <div className="stack" style={{ gap: '1.6rem' }}>
            <AuthAlert>{error}</AuthAlert>
            <button className="btn btn--primary btn--full" onClick={onRequestNewLink}>Get a new link</button>
          </div>
        ) : (
          <form className="stack" style={{ gap: '2.0rem' }} onSubmit={submit}>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input id="new-password" className="input" type="password" autoComplete="new-password"
                value={passwords.first} onChange={set('first')} required />
            </div>
            <div className="field">
              <label htmlFor="new-password-again">New password again</label>
              <input id="new-password-again" className="input" type="password" autoComplete="new-password"
                value={passwords.second} onChange={set('second')} required />
            </div>
            {error && <AuthAlert>{error}</AuthAlert>}
            <button className="btn btn--primary btn--full" disabled={busy}>
              {busy ? 'Saving…' : 'Save new password'}
            </button>
          </form>
        )}
      </div>
      <p className="auth-alt">
        <AuthLinkButton onClick={onShowLogin}>Back to log in</AuthLinkButton>
      </p>
    </AuthLayout>
  )
}
