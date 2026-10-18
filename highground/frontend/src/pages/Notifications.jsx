/** ADR-004: recipient case_event_log rows serve notifications, case history and the audit trail (screen 21). */

import { useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import { useLoad } from '../useLoad'
import { PATHS } from '../icons'
import ResidentShell from './ResidentShell'
import ResponderShell from './ResponderShell'

// Match frozen notification tones: green news, amber household actions and red refusals.
const EVENT_UI = {
  submitted: {
    tone: 'teal',
    path: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
  },
  verified: {
    tone: 'green',
    path: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  needs_info: {
    tone: 'amber',
    path: 'M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z',
  },
  rejected: {
    tone: 'red',
    path: 'M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z',
  },
  claimed: {
    tone: 'teal',
    path: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z',
  },
  closed: {
    tone: 'green',
    path: 'M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z',
  },
  escalated: {
    tone: 'red',
    path: 'M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.732a48.524 48.524 0 01-.005-10.499l-3.11.732a9 9 0 01-6.085-.711l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5',
  },
  // Donations (ADR-025) concern an appeal, not a case.
  donation_recorded: { tone: 'teal', path: PATHS.heart },
  donation_cancelled: { tone: 'amber', path: PATHS.heart },
  donation_received: { tone: 'green', path: PATHS.heart },
}
// Role-application decisions (ADR-027) concern the account itself.
EVENT_UI.application_approved = EVENT_UI.verified
EVENT_UI.application_rejected = EVENT_UI.rejected
EVENT_UI.approval_revoked = EVENT_UI.rejected

const FALLBACK = { tone: 'teal', path: EVENT_UI.verified.path }

// "3 hours ago" reads better than a timestamp for something that just landed.
function ago(iso) {
  const seconds = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export default function Notifications({ user, onLogout, onNavigate, onOpenCase, onOpenAppeals, duplicateCount }) {
  useDocumentTitle('Notifications')
  const [filter, setFilter] = useState('all')
  const [actionError, setActionError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  async function load() {
    const data = await api.notifications()
    setData(data)
  }

  const { data, setData, loading, error: loadError, reload } = useLoad(
    () => api.notifications(), [], { results: [], unread: 0 },
  )
  const rows = data.results
  const unread = data.unread

  async function markRead(id) {
    setActionError(null)
    setBusyId(id)
    try {
      await api.markNotificationRead(id)
      await load()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function markAllRead() {
    setActionError(null)
    setBusyId('all')
    try {
      await api.markAllNotificationsRead()
      await load()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const shown = filter === 'unread' ? rows.filter((r) => !r.read_at) : rows
  // Coordinators share this screen, but must keep their own navigation.
  const Shell = user.role === 'community_member' ? ResidentShell : ResponderShell

  return (
    <Shell
      user={user}
      active="notifications"
      unread={unread}
      counts={{ duplicates: duplicateCount }}
      onNavigate={onNavigate}
      onLogout={onLogout}
    >
      <div className="page-header">
        <div className="row" style={{ gap: '1.2rem', alignItems: 'center' }}>
          <h1>Notifications</h1>
          {unread > 0 && <span className="badge badge--escalated">{unread} unread</span>}
        </div>
        {unread > 0 && (
          <button className="btn btn--ghost btn--sm" onClick={markAllRead} disabled={busyId !== null}>
            {busyId === 'all' ? 'Updating…' : 'Mark all as read'}
          </button>
        )}
      </div>

      <div className="filter-bar">
        {['all', 'unread'].map((key) => (
          <button
            key={key}
            className={`filter-chip${filter === key ? ' filter-chip--active' : ''}`}
            onClick={() => setFilter(key)}
            style={{ background: 'none', font: 'inherit', cursor: 'pointer' }}
          >
            {key === 'all' ? `All · ${rows.length}` : `Unread · ${unread}`}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: 0 }}>
        {loading ? <p role="status" className="text-sm text-muted pad-24">Loading notifications…</p> : loadError ? (
          <p role="alert" className="text-sm pad-24">Could not load notifications: {loadError} <button className="btn btn--ghost btn--sm" onClick={reload}>Retry</button></p>
        ) : shown.length === 0 ? (
          <p className="text-sm text-muted pad-24">
            {filter === 'unread'
              ? 'Nothing unread.'
              : user.role === 'community_member'
                ? 'No notifications yet. You will be told here when your case is reviewed.'
                : 'No notifications yet. Case updates addressed to you will appear here.'}
          </p>
        ) : (
          <ul className="notif-list">
            {shown.map((row) => {
              const ui = EVENT_UI[row.event_type] || FALLBACK
              return (
                <li
                  key={row.id}
                  className={`notif-row${row.read_at ? '' : ' notif-row--unread'}`}
                >
                  <div className={`notif-icon notif-icon--${ui.tone}`}>
                    <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d={ui.path} />
                    </svg>
                  </div>

                  <div className="notif-body">
                    <div className={`notif-title${row.read_at ? ' notif-title--read' : ''}`}>
                      {row.event_display}{row.case_reference && ` · #${row.case_reference}`}
                    </div>
                    <div className="notif-desc">{row.detail}</div>
                    <div className="notif-meta">
                      <span className="notif-time">{ago(row.created_at)}</span>
                      <span className="row gap-12">
                        {(row.case_id || row.donation_id) && (
                          <button
                            className="notif-mark-read"
                            onClick={() => (row.donation_id ? onOpenAppeals() : onOpenCase(row.case_id))}
                            style={{ background: 'none', border: 0, cursor: 'pointer', font: 'inherit' }}
                          >
                            {row.donation_id ? 'View appeal' : 'View case'}
                          </button>
                        )}
                        {!row.read_at && (
                          <button
                            className="notif-mark-read"
                            onClick={() => markRead(row.id)}
                            disabled={busyId !== null}
                            style={{ background: 'none', border: 0, cursor: 'pointer', font: 'inherit' }}
                          >
                            {busyId === row.id ? 'Updating…' : 'Mark as read'}
                          </button>
                        )}
                      </span>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        {actionError && <p role="alert" className="text-sm" style={{ padding: '1rem' }}>Could not update notification: {actionError}</p>}
      </div>
    </Shell>
  )
}
