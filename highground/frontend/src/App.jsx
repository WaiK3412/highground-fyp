import { useEffect, useState } from 'react'
import { api } from './api'
import Login from './pages/Login'
import Register from './pages/Register'
import CaseQueue from './pages/CaseQueue'

// Screens 14 and 19 are the Django admin itself (ADR-002), so admins go there
// rather than to a React shell duplicating it.
const ADMIN_CONSOLE = '/admin/'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [screen, setScreen] = useState('login')
  const [justLoggedIn, setJustLoggedIn] = useState(false)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false))
  }, [])

  // Only jump to the console straight after signing in. Redirecting on every
  // visit would strand an admin with no route back to the login screen.
  useEffect(() => {
    if (justLoggedIn && user?.role === 'system_admin') window.location.assign(ADMIN_CONSOLE)
  }, [justLoggedIn, user])

  async function handleLogout() {
    await api.logout().catch(() => {})
    setUser(null)
    setJustLoggedIn(false)
    setScreen('login')
  }

  function handleLoggedIn(u) {
    setUser(u)
    setJustLoggedIn(true)
  }

  if (checking) return null

  if (user?.role === 'system_admin') {
    return (
      <div className="auth-scene">
        <main className="auth-shell">
          <h1 className="auth-title">Signed in as administrator</h1>
          <p className="auth-sub">{user.full_name} · {user.email}</p>
          <div className="auth-card">
            <div className="stack" style={{ gap: '1.2rem' }}>
              <a className="btn btn--primary btn--full" href={ADMIN_CONSOLE}>
                Open the admin console
              </a>
              <button className="btn btn--ghost btn--full" onClick={handleLogout}>
                Sign out
              </button>
            </div>
          </div>
        </main>
      </div>
    )
  }

  if (user) return <CaseQueue user={user} onLogout={handleLogout} />
  if (screen === 'register')
    return <Register onRegistered={handleLoggedIn} onShowLogin={() => setScreen('login')} />
  return <Login onLoggedIn={handleLoggedIn} onShowRegister={() => setScreen('register')} />
}
