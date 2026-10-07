/** The shared sidebar and page frame for officers and NGO responders. */

import { Icon, PATHS } from '../icons'
import { initials } from '../initials'
import MobileAccount from '../components/MobileAccount'
import ShellNavigation from '../components/ShellNavigation'

// counts: { queue, tasks, duplicates }; each is shown when it is a number.
export default function ResponderShell({
  user, active, unread = 0, counts = {}, onNavigate, onLogout,
  mainClassName = 'main', mainStyle = { maxWidth: '92rem' }, children,
}) {

  const link = (screen) => ({
    href: `#${screen}`,
    className: active === screen ? 'active' : undefined,
    'aria-current': active === screen ? 'page' : undefined,
    onClick: (event) => {
      event.preventDefault()
      onNavigate(screen)
    },
  })
  const count = (value) =>
    typeof value === 'number' && <span className="side-nav__count">{value}</span>
  const isNgo = user.role === 'ngo_volunteer'

  return (
    <div className="app">
      <aside className="sidebar">
        <a {...link('queue')} className="logo" aria-current={undefined}>
          <span className="logo__mark">
            <Icon path={PATHS.logo} strokeWidth={2} />
          </span>
          <span>
            <span className="logo__name">HighGround</span>
            <br />
            <span className="logo__role">{isNgo ? 'NGO responder' : user.role_display}</span>
          </span>
        </a>

        <MobileAccount user={user} onLogout={onLogout} avatarClassName="avatar--info" />

        <ShellNavigation active={active}>
          <a {...link('queue')}>
            <Icon path={PATHS.queue} />
            Case queue
            {count(counts.queue)}
          </a>
          {user.role === 'disaster_officer' && (
            <a {...link('duplicates')}>
              <Icon path={PATHS.duplicates} />
              Duplicate review
              {count(counts.duplicates)}
            </a>
          )}
          {/* Officers can read a case's tasks but do not run an NGO's board. */}
          {isNgo && (
            <a {...link('tasks')}>
              <Icon path={PATHS.tasks} />
              Task board
              {count(counts.tasks)}
            </a>
          )}
          {isNgo && (
            <a {...link('appeals')}>
              <Icon path={PATHS.heart} />
              Supply appeals
            </a>
          )}
          <a {...link('notifications')}>
            <Icon path={PATHS.bell} />
            Notifications
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>
          <a {...link('rules')}>
            <Icon path={PATHS.rules} />
            How priority works
          </a>

          {user.role === 'disaster_officer' ? (
            <>
              {/* Officers act for one district (ADR-024); this is whose cases they see. */}
              <span className="side-nav__label">District</span>
              <span className="side-nav__item side-nav__item--static">
                <Icon path={PATHS.org} />
                {user.district || 'No district assigned'}
              </span>
            </>
          ) : (
            <>
              <span className="side-nav__label">Organisation</span>
              <span className="side-nav__item side-nav__item--static">
                <Icon path={PATHS.org} />
                {user.organization || 'No organisation'}
              </span>
            </>
          )}
        </ShellNavigation>

        <div className="sidebar__user">
          <span className="avatar avatar--info">{initials(user.full_name)}</span>
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
