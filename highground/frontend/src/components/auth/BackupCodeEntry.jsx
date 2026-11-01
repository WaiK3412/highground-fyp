/** Sign in with a one-time backup code instead of the authenticator app (ADR-028). */

import { useState } from 'react'
import { api } from '../../api'
import AuthAlert from './AuthAlert'

export default function BackupCodeEntry({ onVerified, onTimedOut }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onVerified(await api.twoFactorVerifyBackup(code))
    } catch (err) {
      if (err.code === 'pending_expired' && onTimedOut) return onTimedOut(err.message)
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: '1.6rem' }} onSubmit={submit}>
      <div className="field">
        <label htmlFor="backup-code">Backup code</label>
        <input
          id="backup-code"
          className="input"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck="false"
          placeholder="xxxxx-xxxxx"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          autoFocus
          required
        />
      </div>
      {error && <AuthAlert>{error}</AuthAlert>}
      <button className="btn btn--primary btn--full" disabled={busy || !code.trim()}>
        {busy ? 'Checking…' : 'Sign in with backup code'}
      </button>
    </form>
  )
}
