/**
 * Screen 02 — Log in. Markup and classes are the frozen design's; only the
 * static anchor becomes a real form.
 */

import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import AuthAlert from '../components/auth/AuthAlert'
import AuthLayout, { AuthLinkButton } from '../components/auth/AuthLayout'
import ResendConfirmation from '../components/auth/ResendConfirmation'
import TwoFactorCode from '../components/auth/TwoFactorCode'
import TwoFactorSetup from '../components/auth/TwoFactorSetup'

// Staff sign in in two steps (ADR-026): the password, then an authenticator code.
const STEP_TITLES = {
  password: 'Welcome back',
  verify: 'Enter your code',
  setup: 'Set up two-step sign-in',
}

export default function Login({ onLoggedIn, onShowRegister, onShowForgot, notice }) {
  useDocumentTitle('Log in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [unconfirmed, setUnconfirmed] = useState(false)
  const [step, setStep] = useState('password')

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.primeCsrf()
      const result = await api.login(email, password)
      if (result.two_factor) {
        setStep(result.two_factor)
        setBusy(false)
      } else {
        onLoggedIn(result)
      }
    } catch (err) {
      setError(err.message)
      setUnconfirmed(err.code === 'email_unconfirmed')
      setBusy(false)
    }
  }

  function backToPassword(message) {
    setStep('password')
    setPassword('')
    setError(message)
  }

  return (
    <AuthLayout
      title={STEP_TITLES[step]}
      subtitle={step === 'password' ? 'One shared view of every recovery case — for residents, NGOs, and district officers.' : null}
    >
      <div className="auth-card">
        {step === 'verify' && <TwoFactorCode onVerified={onLoggedIn} onTimedOut={backToPassword} />}
        {step === 'setup' && <TwoFactorSetup onVerified={onLoggedIn} onTimedOut={backToPassword} />}
        {step === 'password' && (
          <form className="stack" style={{ gap: '2.0rem' }} onSubmit={handleSubmit}>
            {notice && <AuthAlert tone="success">{notice}</AuthAlert>}
            <div className="field">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="username"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {error && <AuthAlert>{error}</AuthAlert>}

            <button className="btn btn--primary btn--full" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Log in'}
            </button>
            <p className="text-sm" style={{ margin: 0, textAlign: 'center' }}>
              <button type="button" className="link-button" style={{ color: 'var(--teal-700)', fontWeight: 600 }} onClick={onShowForgot}>
                Forgot password?
              </button>
            </p>
          </form>
        )}
        {unconfirmed && (
          <div style={{ marginTop: '1.6rem' }}>
            <ResendConfirmation email={email} />
          </div>
        )}
      </div>

      <p className="auth-alt">
        New to HighGround?{' '}
        <AuthLinkButton onClick={onShowRegister}>Create an account</AuthLinkButton>
      </p>

      <div className="auth-note">
        <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
          />
        </svg>
        <span>
          <span className="title">Need urgent help during a flood?</span> Call the NADMA hotline at
          999 or use MyDIMS for emergency alerts. HighGround is for post-flood recovery assistance.
        </span>
      </div>
    </AuthLayout>
  )
}
