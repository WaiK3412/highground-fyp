/**
 * The 6-digit authenticator code (ADR-026). By default it finishes signing in;
 * the Profile settings pass `verify` to turn two-step sign-in on or off instead.
 */

import { useState } from 'react'
import { api } from '../../api'
import AuthAlert from './AuthAlert'

export default function TwoFactorCode({
  onVerified, onTimedOut, verify = api.twoFactorVerify, buttonLabel = 'Verify and sign in',
}) {
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onVerified(await verify(code))
    } catch (err) {
      // Waited too long after the password: start again from the password step.
      if (err.code === 'pending_expired' && onTimedOut) return onTimedOut(err.message)
      setError(err.message)
      setCode('')
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: '1.6rem' }} onSubmit={submit}>
      <div className="field">
        <label htmlFor="two-factor-code">6-digit code from your authenticator app</label>
        <input
          id="two-factor-code"
          className="input"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength="6"
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
          autoFocus
          required
        />
      </div>
      {error && <AuthAlert>{error}</AuthAlert>}
      <button className="btn btn--primary btn--full" disabled={busy || code.length !== 6}>
        {busy ? 'Checking…' : buttonLabel}
      </button>
    </form>
  )
}
