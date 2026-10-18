/** Ask for a password-reset link. The answer is the same whether or not the address has an account. */

import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import AuthAlert from '../components/auth/AuthAlert'
import AuthLayout, { AuthLinkButton } from '../components/auth/AuthLayout'

export default function ForgotPassword({ onShowLogin }) {
  useDocumentTitle('Forgot password')
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.primeCsrf()
      setSent((await api.requestPasswordReset(email)).detail)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Forgot your password?" subtitle="We will email you a link to choose a new one.">
      <div className="auth-card">
        {sent ? (
          <AuthAlert tone="success">{sent} The link works for one hour.</AuthAlert>
        ) : (
          <form className="stack" style={{ gap: '2.0rem' }} onSubmit={submit}>
            <div className="field">
              <label htmlFor="reset-email">Email address</label>
              <input
                id="reset-email"
                className="input"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            {error && <AuthAlert>{error}</AuthAlert>}
            <button className="btn btn--primary btn--full" disabled={busy}>
              {busy ? 'Sending…' : 'Email me a link'}
            </button>
          </form>
        )}
      </div>
      <p className="auth-alt">
        Remembered it? <AuthLinkButton onClick={onShowLogin}>Back to log in</AuthLinkButton>
      </p>
    </AuthLayout>
  )
}
