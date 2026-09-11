import { useEffect, useState } from 'react'
import { api } from './api'
import Login from './pages/Login'
import Register from './pages/Register'
import CaseQueue from './pages/CaseQueue'
import ResidentDashboard from './pages/ResidentDashboard'
import SubmitRequest from './pages/SubmitRequest'
import Notifications from './pages/Notifications'
import ScoringRules from './pages/ScoringRules'

// Screens 14 and 19 are the Django admin itself (ADR-002), so admins go there
// rather than to a React shell duplicating it.
const ADMIN_CONSOLE = '/admin/'

// The rules page has no chrome of its own; wrap it in the plain app frame with
// a way back to the queue.
function ResponderRules({ user, onLogout, onBack }) {
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#queue" onClick={(e) => { e.preventDefault(); onBack() }}>
          <span className="name">HighGround</span>
        </a>
        <nav className="side-nav">
          <a href="#queue" onClick={(e) => { e.preventDefault(); onBack() }}>
            Case queue
          </a>
          <a href="#rules" className="active" onClick={(e) => e.preventDefault()}>
            How scoring works
          </a>
        </nav>
        <div className="sidebar__user">
          <div>
            <div className="text-sm text-strong">{user.full_name}</div>
            <button
              className="text-xs text-muted"
              onClick={onLogout}
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="main" style={{ maxWidth: '92rem' }}>
        <ScoringRules />
      </main>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [screen, setScreen] = useState('login')
  const [justLoggedIn, setJustLoggedIn] = useState(false)
  // Residents have two screens now; anything more and this wants a router.
  const [residentScreen, setResidentScreen] = useState('recovery')
  // Officers and NGOs have their own small set of screens.
  const [responderScreen, setResponderScreen] = useState('queue')

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

  // A resident — including someone whose role application is still pending,
  // since ADR-012 leaves them least-privileged until an admin decides — gets
  // their own household screen, not the responder queue.
  if (user?.role === 'community_member') {
    if (residentScreen === 'submit')
      return (
        <SubmitRequest
          user={user}
          onLogout={handleLogout}
          onCancel={() => setResidentScreen('recovery')}
          onSubmitted={() => setResidentScreen('recovery')}
        />
      )
    if (residentScreen === 'notifications')
      return (
        <Notifications
          user={user}
          onLogout={handleLogout}
          onNavigate={setResidentScreen}
          onOpenCase={() => setResidentScreen('recovery')}
        />
      )
    return (
      <ResidentDashboard
        user={user}
        onLogout={handleLogout}
        onSubmitRequest={() => setResidentScreen('submit')}
        onNavigate={setResidentScreen}
      />
    )
  }

  if (user) {
    if (responderScreen === 'notifications')
      return (
        <Notifications
          user={user}
          onLogout={handleLogout}
          onNavigate={() => setResponderScreen('queue')}
          onOpenCase={() => setResponderScreen('queue')}
        />
      )
    if (responderScreen === 'rules')
      return (
        <ResponderRules user={user} onLogout={handleLogout} onBack={() => setResponderScreen('queue')} />
      )
    return <CaseQueue user={user} onLogout={handleLogout} onNavigate={setResponderScreen} />
  }
  if (screen === 'register')
    return <Register onRegistered={handleLoggedIn} onShowLogin={() => setScreen('login')} />
  return <Login onLoggedIn={handleLoggedIn} onShowRegister={() => setScreen('register')} />
}
