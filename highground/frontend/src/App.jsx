import { useEffect, useState } from 'react'
import { api } from './api'
import { homePath, isAllowed, parsePath, pathFor } from './routes'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import ConfirmEmail from './pages/ConfirmEmail'
import PolicyPage from './pages/PolicyPage'
import CaseQueue from './pages/CaseQueue'
import TaskBoard from './pages/TaskBoard'
import ResidentDashboard from './pages/ResidentDashboard'
import SubmitRequest from './pages/SubmitRequest'
import Notifications from './pages/Notifications'
import PriorityRules from './pages/PriorityRules'
import ResponderShell from './pages/ResponderShell'
import DuplicateReview from './pages/DuplicateReview'
import SupplyAppeals from './pages/SupplyAppeals'
import Profile from './pages/Profile'
import ResidentShell from './pages/ResidentShell'

// Screens 14 and 19 are the Django admin itself (ADR-002), so admins go there
// rather than to a React shell duplicating it.
const ADMIN_CONSOLE = '/admin/'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [bootError, setBootError] = useState(null)
  const [justLoggedIn, setJustLoggedIn] = useState(false)
  // The address bar decides the screen (routes.js), so Back, Forward and reload work.
  const [route, setRoute] = useState(() => parsePath(window.location.pathname))
  const [duplicateCount, setDuplicateCount] = useState(null)
  // Good news to show on the login screen, e.g. after a password reset.
  const [loginNotice, setLoginNotice] = useState(null)

  function go(path, { replace = false, state = null } = {}) {
    window.history[replace ? 'replaceState' : 'pushState'](state, '', path)
    setRoute(parsePath(path))
  }

  // `returnTo` rides in the history entry: where to go once the person signs in.
  function navigate(screen, params = {}, { replace = false, returnTo = null } = {}) {
    go(pathFor(screen, params), { replace, state: returnTo ? { returnTo } : null })
  }

  useEffect(() => {
    const onPop = () => setRoute(parsePath(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Someone at an address their role cannot use is shown where they can go:
  // signed-out visitors the login (and their address afterwards), everyone
  // else their home screen. Worked out while rendering; the effect only
  // corrects the address bar, without adding a history entry.
  const role = user?.role ?? null
  const redirect = !checking && !bootError && !isAllowed(role, route.screen)
    ? (!user && route.screen ? pathFor('login') : homePath(role))
    : null
  const current = redirect ? parsePath(redirect) : route

  useEffect(() => {
    if (!redirect) return
    const returnTo = !user && redirect === pathFor('login') ? window.location.pathname : null
    window.history.replaceState(returnTo ? { returnTo } : null, '', redirect)
  }, [redirect, user])

  useEffect(() => {
    if (user?.role !== 'disaster_officer') return undefined
    let cancelled = false
    api.duplicates().then((data) => {
      if (!cancelled) setDuplicateCount(data.count)
    }).catch(() => {
      if (!cancelled) setDuplicateCount(null)
    })
    return () => { cancelled = true }
  }, [user, route.screen])

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
    setDuplicateCount(null)
    go(pathFor('landing'), { replace: true })
  }

  function handleLoggedIn(u) {
    const returnTo = window.history.state?.returnTo
    const wanted = returnTo && isAllowed(u.role, parsePath(returnTo).screen) ? returnTo : homePath(u.role)
    setUser(u)
    setJustLoggedIn(true)
    go(wanted, { replace: true })
  }

  // The open case of a list screen, kept in the address (/my-cases/42) so the
  // phone's Back button closes it instead of leaving the screen.
  function caseRouteFor(listScreen) {
    return {
      id: current.screen === listScreen ? current.id : null,
      open(id) {
        if (current.id != null) go(pathFor(listScreen, { id }), { replace: true, state: window.history.state })
        else go(pathFor(listScreen, { id }), { state: { openedFromList: true } })
      },
      close() {
        // Opened from the list: step back to it. Opened from a link: there is nothing to go back to.
        if (window.history.state?.openedFromList) window.history.back()
        else go(pathFor(listScreen), { replace: true })
      },
      clear() {
        go(pathFor(listScreen), { replace: true })
      },
    }
  }

  if (checking) return <main className="auth-shell"><p role="status">Checking your session…</p></main>
  if (bootError) return (
    <main className="auth-shell">
      <p role="alert">{bootError}</p>
      <button className="btn btn--primary" onClick={refreshSession}>Retry</button>
    </main>
  )

  const screen = current.screen
  const show = (next) => navigate(next)

  // Email links open whether or not someone is signed in on this browser.
  if (screen === 'reset')
    return (
      <ResetPassword
        uid={current.uid}
        token={current.token}
        onDone={(notice) => { setLoginNotice(notice); navigate('login', {}, { replace: true }) }}
        onRequestNewLink={() => navigate('forgot')}
        onShowLogin={() => navigate('login')}
      />
    )

  if (screen === 'confirm')
    return <ConfirmEmail token={current.token} onShowLogin={() => navigate('login')} />

  // The terms and the privacy notice read the same for everyone. Registration
  // opens them in a new tab, so "Back" there would leave the app: go home instead.
  if (screen === 'terms' || screen === 'privacy')
    return (
      <PolicyPage
        kind={screen}
        backLabel="Back to HighGround"
        onBack={() => (window.history.length > 1 ? window.history.back() : window.location.assign(homePath(user?.role)))}
      />
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
    if (screen === 'submit')
      return (
        <SubmitRequest
          user={user}
          onLogout={handleLogout}
          onCancel={() => navigate('recovery')}
          onSubmitted={() => navigate('recovery')}
          onNavigate={show}
        />
      )
    if (screen === 'profile')
      return (
        <ResidentShell user={user} active="profile" onNavigate={show} onLogout={handleLogout}>
          <Profile user={user} onSaved={setUser} />
        </ResidentShell>
      )
    if (screen === 'appeals')
      return (
        <ResidentShell user={user} active="appeals" onNavigate={show} onLogout={handleLogout}>
          <SupplyAppeals user={user} />
        </ResidentShell>
      )
    if (screen === 'notifications')
      return (
        <Notifications
          user={user}
          onLogout={handleLogout}
          onNavigate={show}
          onOpenCase={(id) => navigate('recovery', { id })}
          onOpenAppeals={() => navigate('appeals')}
        />
      )
    return (
      <ResidentDashboard
        user={user}
        onLogout={handleLogout}
        onSubmitRequest={() => navigate('submit')}
        onNavigate={show}
        caseRoute={caseRouteFor('recovery')}
      />
    )
  }

  if (user) {
    if (screen === 'tasks' && user.role === 'ngo_volunteer')
      return <TaskBoard user={user} onLogout={handleLogout} onNavigate={show} />
    if (screen === 'notifications')
      return (
        <Notifications
          user={user}
          onLogout={handleLogout}
          onNavigate={show}
          onOpenCase={(id) => navigate('queue', { id })}
          onOpenAppeals={() => navigate('appeals')}
          duplicateCount={duplicateCount}
        />
      )
    // The rules page has no chrome of its own; it sits in the responder frame.
    if (screen === 'rules')
      return (
        <ResponderShell user={user} active="rules" onNavigate={show} onLogout={handleLogout} counts={{ duplicates: duplicateCount }}>
          <PriorityRules />
        </ResponderShell>
      )
    if (screen === 'appeals')
      return (
        <ResponderShell user={user} active="appeals" onNavigate={show} onLogout={handleLogout} counts={{ duplicates: duplicateCount }}>
          <SupplyAppeals user={user} />
        </ResponderShell>
      )
    if (screen === 'duplicates' && user.role === 'disaster_officer')
      return (
        <DuplicateReview
          key={current.id ?? 'list'}
          user={user}
          initialId={current.id}
          duplicateCount={duplicateCount}
          onCountChange={setDuplicateCount}
          onNavigate={show}
          onLogout={handleLogout}
        />
      )
    return (
      <CaseQueue
        user={user}
        onLogout={handleLogout}
        onNavigate={show}
        onOpenDuplicate={(id) => navigate('duplicates', { id })}
        duplicateCount={duplicateCount}
        caseRoute={caseRouteFor('queue')}
      />
    )
  }

  if (screen === 'register')
    return <Register onShowLogin={() => navigate('login')} />
  if (screen === 'forgot') return <ForgotPassword onShowLogin={() => navigate('login')} />
  if (screen === 'landing')
    return (
      <Landing
        onShowLogin={() => navigate('login')}
        onShowRegister={() => navigate('register')}
        onDonate={() => navigate('login', {}, { returnTo: pathFor('appeals') })}
      />
    )
  return (
    <Login
      notice={loginNotice}
      onLoggedIn={(u) => { setLoginNotice(null); handleLoggedIn(u) }}
      onShowRegister={() => navigate('register')}
      onShowForgot={() => navigate('forgot')}
    />
  )
}
