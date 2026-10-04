/**
 * Screen 02 — Log in. Markup and classes are the frozen design's; only the
 * static anchor becomes a real form.
 */

import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

const CONTOUR =
  'M-220 -30 C-210 -130 -100 -200 20 -195 C140 -190 225 -110 228 -5 C231 100 150 190 20 200 C-110 210 -230 130 -220 -30 Z'

function Contours({ modifier, scales }) {
  return (
    <svg
      className={`auth-scene__contours auth-scene__contours--${modifier}`}
      viewBox="0 0 600 600"
      aria-hidden="true"
      fill="none"
      stroke="#FFFFFF"
      strokeWidth="1.5"
    >
      <g transform="translate(300 300)">
        {scales.map(([scale, opacity]) => (
          <path
            key={scale}
            transform={scale === 1 ? undefined : `scale(${scale})`}
            d={CONTOUR}
            opacity={opacity}
          />
        ))}
      </g>
    </svg>
  )
}

export default function Login({ onLoggedIn, onShowRegister }) {
  useDocumentTitle('Log in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.primeCsrf()
      const user = await api.login(email, password)
      onLoggedIn(user)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="auth-scene">
      <Contours modifier="tl" scales={[[1, 0.05], [0.8, 0.07], [0.6, 0.09], [0.42, 0.11]]} />
      <Contours modifier="br" scales={[[1, 0.05], [0.7, 0.08], [0.45, 0.11]]} />

      <svg className="auth-scene__ridge" viewBox="0 0 1440 110" preserveAspectRatio="none" aria-hidden="true">
        <path
          d="M0 74 C 240 44, 430 88, 720 64 C 990 44, 1210 90, 1440 60 L1440 110 L0 110 Z"
          fill="rgba(233, 220, 195, 0.10)"
        />
        <path
          d="M0 60 C 240 32, 430 74, 720 52 C 990 34, 1210 78, 1440 46"
          fill="none"
          stroke="rgba(233, 220, 195, 0.22)"
          strokeWidth="1.5"
        />
      </svg>

      <main className="auth-shell">
        <span className="auth-brand">
          <span className="logo__mark">
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0"
              />
            </svg>
          </span>
          <span className="name">HighGround</span>
        </span>

        <h1 className="auth-title">Welcome back</h1>
        <p className="auth-sub">
          One shared view of every recovery case — for residents, NGOs, and district officers.
        </p>

        <div className="auth-card">
          <form className="stack" style={{ gap: '2.0rem' }} onSubmit={handleSubmit}>
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

            {error && (
              <div
                role="alert"
                style={{
                  background: 'var(--danger-100)',
                  color: 'var(--danger-600)',
                  padding: '1.0rem 1.2rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--fs-14)',
                  fontWeight: 600,
                }}
              >
                {error}
              </div>
            )}

            <button className="btn btn--primary btn--full" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Log in'}
            </button>
          </form>
        </div>

        <p className="auth-alt">
          New to HighGround?{' '}
          <button
            onClick={onShowRegister}
            style={{
              background: 'none',
              border: 0,
              padding: 0,
              cursor: 'pointer',
              color: 'var(--teal-300)',
              fontWeight: 600,
              font: 'inherit',
            }}
          >
            Create an account
          </button>
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
      </main>
    </div>
  )
}
