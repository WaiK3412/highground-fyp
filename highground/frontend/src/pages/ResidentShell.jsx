/**
 * The resident sidebar and page frame.
 *
 * Extracted when Notifications became the third screen to need it. My Recovery
 * and Submit a request still carry their own copies — they were written before
 * this existed and are working, so they are left alone rather than refactored
 * mid-phase. Worth folding them in when one of them next needs changing.
 */

const PATHS = {
  logo: 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0',
  home: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75',
  plus: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
  folder: 'M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z',
  bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0',
  heart: 'M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z',
  user: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
}

function Icon({ path, strokeWidth = 1.5 }) {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth={strokeWidth} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  )
}

export default function ResidentShell({ user, active, unread = 0, onNavigate, onLogout, children }) {
  const initials = (user.full_name || '?')
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')

  const go = (screen) => (event) => {
    event.preventDefault()
    onNavigate(screen)
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#recovery" onClick={go('recovery')}>
          <span className="logo__mark">
            <Icon path={PATHS.logo} strokeWidth={2} />
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">Resident</span>
          </span>
        </a>

        <nav className="side-nav">
          <a
            href="#recovery"
            className={active === 'recovery' ? 'active' : undefined}
            onClick={go('recovery')}
          >
            <Icon path={PATHS.home} />
            My Recovery
          </a>
          <a
            href="#submit"
            className={active === 'submit' ? 'active' : undefined}
            onClick={go('submit')}
          >
            <Icon path={PATHS.plus} />
            Submit a request
          </a>
          <a href="#cases" onClick={go('recovery')}>
            <Icon path={PATHS.folder} />
            My cases
          </a>
          <a
            href="#notifications"
            className={active === 'notifications' ? 'active' : undefined}
            onClick={go('notifications')}
          >
            <Icon path={PATHS.bell} />
            Notifications
            {/* Counts are teal-tinted, never red — red is reserved for status
                (DESIGN-GUIDE §4, Navigation). */}
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>

          <span className="side-nav__label">Community</span>
          <span className="side-nav__item side-nav__item--soon" aria-disabled="true">
            <Icon path={PATHS.heart} />
            Pledge supplies <span className="side-nav__soon-tag">Coming soon</span>
          </span>

          <span className="side-nav__label">Account</span>
          <a href="#profile" onClick={(e) => e.preventDefault()}>
            <Icon path={PATHS.user} />
            My profile
          </a>
        </nav>

        <div className="sidebar__user">
          <span className="avatar">{initials}</span>
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
        {children}
      </main>
    </div>
  )
}
