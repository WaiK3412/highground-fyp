/**
 * The responder sidebar and page frame, for officers and NGO responders.
 *
 * Added so Notifications stops showing the resident sidebar to coordinators.
 * The case queue and task board still carry their own copies of this sidebar;
 * like ResidentShell, those are worth folding in when one of them next needs
 * changing rather than refactored mid-phase.
 */

const PATHS = {
  logo: 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0',
  queue: 'M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z',
  tasks: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z',
  bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0',
  rules: 'M3 6.75A2.25 2.25 0 015.25 4.5h13.5A2.25 2.25 0 0121 6.75v10.5A2.25 2.25 0 0118.75 19.5H5.25A2.25 2.25 0 013 17.25V6.75zM7.5 9h9M7.5 12h9M7.5 15h5.25',
  org: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.75c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
}

function Icon({ path, strokeWidth = 1.5 }) {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth={strokeWidth} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  )
}

export default function ResponderShell({ user, active, unread = 0, onNavigate, onLogout, children }) {
  const initials = (user.full_name || '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  const go = (screen) => (event) => {
    event.preventDefault()
    onNavigate(screen)
  }
  const current = (screen) => (active === screen ? 'active' : undefined)

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#queue" onClick={go('queue')}>
          <span className="logo__mark">
            <Icon path={PATHS.logo} strokeWidth={2} />
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">
              {user.role === 'ngo_volunteer' ? 'NGO responder' : user.role_display}
            </span>
          </span>
        </a>

        <nav className="side-nav">
          <a href="#queue" className={current('queue')} onClick={go('queue')}>
            <Icon path={PATHS.queue} />
            Case queue
          </a>
          {/* Officers can read a case's tasks but do not run an NGO's board. */}
          {user.role === 'ngo_volunteer' && (
            <a href="#tasks" className={current('tasks')} onClick={go('tasks')}>
              <Icon path={PATHS.tasks} />
              Task board
            </a>
          )}
          <a href="#notifications" className={current('notifications')} onClick={go('notifications')}>
            <Icon path={PATHS.bell} />
            Notifications
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>
          <a href="#rules" className={current('rules')} onClick={go('rules')}>
            <Icon path={PATHS.rules} />
            How scoring works
          </a>

          <span className="side-nav__label">Organisation</span>
          <span className="side-nav__item side-nav__item--static">
            <Icon path={PATHS.org} />
            {user.organization || 'No organisation'}
          </span>
        </nav>

        <div className="sidebar__user">
          <span className="avatar avatar--info">{initials}</span>
          <div>
            <div className="text-sm text-strong">{user.full_name}</div>
            <button
              className="text-xs text-muted"
              onClick={onLogout}
              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', fontFamily: 'inherit' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="main" style={{ maxWidth: '92rem' }}>
        {children}
      </main>
    </div>
  )
}
