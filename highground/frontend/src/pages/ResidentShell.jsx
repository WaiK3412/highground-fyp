/** The shared resident sidebar and page frame. */

import { Icon, PATHS } from '../icons'
import { useUnreadCount } from '../useUnreadCount'
import { pathFor } from '../routes'
import { initials } from '../initials'
import MobileAccount from '../components/MobileAccount'
import ShellNavigation from '../components/ShellNavigation'

export default function ResidentShell({
  user, active, unread, onNavigate, onLogout,
  mainClassName = 'main', mainStyle = { maxWidth: '92rem' }, children,
}) {
  // The notifications screen passes its own live count; elsewhere the shell keeps it fresh.
  const polledUnread = useUnreadCount({ enabled: unread === undefined })
  const unreadCount = unread ?? polledUnread

  const link = (screen) => ({
    href: pathFor(screen),
    className: active === screen ? 'active' : undefined,
    'aria-current': active === screen ? 'page' : undefined,
    onClick: (event) => {
      event.preventDefault()
      onNavigate(screen)
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

        <MobileAccount user={user} onLogout={onLogout} />

        <ShellNavigation active={active}>
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
          {/* No separate "My cases" item (unlike the design prototype): the case list
              lives on My Recovery, so a second link to the same screen looked broken. */}
          <a {...link('notifications')}>
            <Icon path={PATHS.bell} />
            Notifications
            {/* Counts are teal-tinted, never red — red is reserved for status
                (DESIGN-GUIDE §4, Navigation). */}
            {unreadCount > 0 && <span className="side-nav__count">{unreadCount}</span>}
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
        </ShellNavigation>

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
