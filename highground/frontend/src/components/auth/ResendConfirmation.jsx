/** "Send the confirmation email again", for an address given or typed in. */

import { useState } from 'react'
import { api } from '../../api'
import AuthAlert from './AuthAlert'

export default function ResendConfirmation({ email: knownEmail = '' }) {
  const [email, setEmail] = useState(knownEmail)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  async function resend(event) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.primeCsrf()
      setResult({ tone: 'success', text: (await api.resendConfirmation(email)).detail })
    } catch (err) {
      setResult({ tone: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: '1.2rem' }} onSubmit={resend}>
      {!knownEmail && (
        <div className="field">
          <label htmlFor="resend-email">Email address</label>
          <input id="resend-email" className="input" type="email" value={email}
            onChange={(event) => setEmail(event.target.value)} required />
        </div>
      )}
      {result && <AuthAlert tone={result.tone}>{result.text}</AuthAlert>}
      <button className="btn btn--secondary btn--full" disabled={busy}>
        {busy ? 'Sending…' : 'Resend the confirmation email'}
      </button>
    </form>
  )
}
