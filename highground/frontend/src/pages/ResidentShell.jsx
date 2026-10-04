/** The shared resident sidebar and page frame. */

import { Icon, PATHS } from '../icons'
import { initials } from '../initials'

export default function ResidentShell({
  user, active, unread = 0, casesCount = 0, onNavigate, onLogout,
  mainClassName = 'main', mainStyle = { maxWidth: '92rem' }, children,
}) {

  // `target` lets "My cases" open My Recovery, where the case list lives.
  const link = (screen, target = screen) => ({
    href: `#${screen}`,
    className: active === screen ? 'active' : undefined,
    'aria-current': active === screen ? 'page' : undefined,
    onClick: (event) => {
      event.preventDefault()
      onNavigate(target)
    },
  })

  return (
    <div className="app">
      <aside className="sidebar">
        <a {...link('recovery')} className="logo" aria-current={undefined}>
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
          {/* "My Recovery", not "Dashboard": the design contract and report §2.2.4
              use household language; responder screens use operational terms. */}
          <a {...link('recovery')}>
            <Icon path={PATHS.home} />
            My Recovery
          </a>
          <a {...link('submit')}>
            <Icon path={PATHS.request} />
            Submit a request
          </a>
          <a {...link('cases', 'recovery')}>
            <Icon path={PATHS.folder} />
            My cases
            {casesCount > 0 && <span className="side-nav__count">{casesCount}</span>}
          </a>
          <a {...link('notifications')}>
            <Icon path={PATHS.bell} />
            Notifications
            {/* Counts are teal-tinted, never red — red is reserved for status
                (DESIGN-GUIDE §4, Navigation). */}
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>

          <span className="side-nav__label">Community</span>
          <a {...link('appeals')}>
            <Icon path={PATHS.heart} />
            Supplies needed
          </a>

          <span className="side-nav__label">Account</span>
          <a {...link('profile')}>
            <Icon path={PATHS.user} />
            My profile
          </a>
        </nav>

        <div className="sidebar__user">
          <span className="avatar">{initials(user.full_name)}</span>
          <div>
            <div className="text-sm text-strong">{user.full_name}</div>
            <button className="link-button text-xs text-muted" onClick={onLogout}>
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className={mainClassName} style={mainStyle}>
        {children}
      </main>
    </div>
  )
}
