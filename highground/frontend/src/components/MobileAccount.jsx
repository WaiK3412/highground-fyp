import { useId, useRef, useState } from 'react'
import { initials } from '../initials'

export default function MobileAccount({ user, onLogout, avatarClassName = '' }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const toggle = useRef(null)

  return (
    <div
      className="mobile-account"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setOpen(false)
          toggle.current.focus()
        }
      }}
    >
      <button
        ref={toggle}
        type="button"
        className={`avatar mobile-account__toggle ${avatarClassName}`}
        aria-label={`Account for ${user.full_name}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {initials(user.full_name)}
      </button>
      <div id={panelId} className="mobile-account__panel" hidden={!open}>
        <p className="text-sm text-strong">{user.full_name}</p>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </div>
  )
}
