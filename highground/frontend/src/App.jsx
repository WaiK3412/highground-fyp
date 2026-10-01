import { useEffect, useState } from 'react'
import { api } from './api'
import Login from './pages/Login'
import Register from './pages/Register'
import CaseQueue from './pages/CaseQueue'
import TaskBoard from './pages/TaskBoard'
import ResidentDashboard from './pages/ResidentDashboard'
import SubmitRequest from './pages/SubmitRequest'
import Notifications from './pages/Notifications'
import PriorityRules from './pages/PriorityRules'
import ResponderShell from './pages/ResponderShell'
import DuplicateReview from './pages/DuplicateReview'

// Screens 14 and 19 are the Django admin itself (ADR-002), so admins go there
// rather than to a React shell duplicating it.
const ADMIN_CONSOLE = '/admin/'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [bootError, setBootError] = useState(null)
  const [screen, setScreen] = useState('login')
  const [justLoggedIn, setJustLoggedIn] = useState(false)
  // Residents have two screens now; anything more and this wants a router.
  const [residentScreen, setResidentScreen] = useState('recovery')
  // Officers and NGOs have their own small set of screens.
  const [responderScreen, setResponderScreen] = useState('queue')
  const [duplicateId, setDuplicateId] = useState(null)
  const [duplicateCount, setDuplicateCount] = useState(null)

  useEffect(() => {
    if (user?.role !== 'disaster_officer') return undefined
    let cancelled = false
    api.duplicates().then((data) => {
      if (!cancelled) setDuplicateCount(data.count)
    }).catch(() => {
      if (!cancelled) setDuplicateCount(null)
    })
    return () => { cancelled = true }
  }, [user, responderScreen])

  function navigateResponder(next) {
    if (next === 'duplicates') setDuplicateId(null)
    setResponderScreen(next)
  }

  function openDuplicate(id) {
    setDuplicateId(id)
    setResponderScreen('duplicates')
  }

  async function refreshSession() {
    setChecking(true)
    setBootError(null)
    try {
      setUser(await api.me())
    } catch (err) {
      if (err.status === 401 || err.status === 403) setUser(null)
      else setBootError('Could not connect to HighGround. Check your connection and try again.')
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    api.me()
      .then(setUser)
      .catch((err) => {
        if (err.status === 401 || err.status === 403) setUser(null)
        else setBootError('Could not connect to HighGround. Check your connection and try again.')
      })
      .finally(() => setChecking(false))
  }, [])

  // Only jump to the console straight after signing in. Redirecting on every
  // visit would strand an admin with no route back to the login screen.
  useEffect(() => {
    if (justLoggedIn && user?.role === 'system_admin') window.location.assign(ADMIN_CONSOLE)
  }, [justLoggedIn, user])

  async function handleLogout() {
    try {
      await api.logout()
    } catch {
      setBootError('Could not sign out. Please try again.')
      return
    }
    setUser(null)
    setJustLoggedIn(false)
    setScreen('login')
    setResponderScreen('queue')
    setDuplicateId(null)
    setDuplicateCount(null)
  }

  function handleLoggedIn(u) {
    setUser(u)
    setJustLoggedIn(true)
  }

  if (checking) return <main className="auth-shell"><p role="status">Checking your session…</p></main>
  if (bootError) return (
    <main className="auth-shell">
      <p role="alert">{bootError}</p>
      <button className="btn btn--primary" onClick={refreshSession}>Retry</button>
    </main>
  )

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
    if (responderScreen === 'tasks' && user.role === 'ngo_volunteer')
      return (
        <TaskBoard
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateResponder}
        />
      )
    if (responderScreen === 'notifications')
      return (
        <Notifications
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateResponder}
          onOpenCase={() => setResponderScreen('queue')}
          duplicateCount={duplicateCount}
        />
      )
    // The rules page has no chrome of its own; it sits in the responder frame.
    if (responderScreen === 'rules')
      return (
        <ResponderShell user={user} active="rules" onNavigate={navigateResponder} onLogout={handleLogout} duplicateCount={duplicateCount}>
          <PriorityRules />
        </ResponderShell>
      )
    if (responderScreen === 'duplicates' && user.role === 'disaster_officer')
      return (
        <DuplicateReview
          user={user}
          initialId={duplicateId}
          duplicateCount={duplicateCount}
          onCountChange={setDuplicateCount}
          onNavigate={navigateResponder}
          onLogout={handleLogout}
        />
      )
    return <CaseQueue user={user} onLogout={handleLogout} onNavigate={navigateResponder} onOpenDuplicate={openDuplicate} duplicateCount={duplicateCount} />
  }
  if (screen === 'register')
    return <Register onRegistered={handleLoggedIn} onShowLogin={() => setScreen('login')} />
  return <Login onLoggedIn={handleLoggedIn} onShowRegister={() => setScreen('register')} />
}
