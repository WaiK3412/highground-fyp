/**
 * Screen 09 — the claiming NGO's task board.
 *
 * The frozen prototype showed several volunteers and percentage progress. The
 * accepted v1 deliberately uses one accountable responder and auditable state
 * changes instead: open/assigned, in progress, done, then resident confirmation.
 *
 * Layout follows design-prototype-v2/screens/09-ngo-task-board.html: three
 * columns on a 3px status rail, a card per task, the score chip from the queue.
 * Assignment and progress notes open in place so a card at rest stays a card.
 */

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

const TASK_TYPES = [
  ['cleanup', 'Cleanup'],
  ['repair', 'Repair'],
  ['delivery', 'Delivery'],
  ['assessment', 'Assessment'],
]

const PATHS = {
  logo: 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0',
  queue: 'M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z',
  tasks: 'M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z',
  bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a3 3 0 11-5.714 0',
  rules: 'M3 6.75A2.25 2.25 0 015.25 4.5h13.5A2.25 2.25 0 0121 6.75v10.5A2.25 2.25 0 0118.75 19.5H5.25A2.25 2.25 0 013 17.25V6.75zM7.5 9h9M7.5 12h9M7.5 15h5.25',
  org: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.75c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
  check: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  warn: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z',
}

// One glyph per task type, as on the design contract's card header.
const TYPE_PATHS = {
  cleanup:
    'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 8.5a4 4 0 01-3 3.5 4 4 0 01-3-3.5L8 4z',
  repair:
    'M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085',
  delivery: 'M21 7.5l-9-5.25L3 7.5m18 0l-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9',
  assessment:
    'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
}

// The task's own state, in the badge vocabulary the rest of the app uses.
const STATUS_BADGE = {
  open: 'badge--new',
  assigned: 'badge--assigned',
  in_progress: 'badge--progress',
  done: 'badge--resolved',
}

function Icon({ path }) {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  )
}

function initials(name) {
  return name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
}

// Same three bands as the case queue, so a score reads the same on both screens.
function scoreClass(band) {
  if (band === 'High') return 'score score--high score--sm'
  if (band === 'Medium') return 'score score--medium score--sm'
  return 'score score--low score--sm'
}

function errorText(err) {
  const fields = err.fields || {}
  for (const key of ['safety_acknowledged', 'status', 'lead_user_id', 'safety_note', 'detail']) {
    if (fields[key]) return Array.isArray(fields[key]) ? fields[key].join(' ') : String(fields[key])
  }
  return err.message
}

function TaskCard({ task, responders, currentUserId, onChanged }) {
  // Only one of the two forms is open at a time, so a card at rest shows
  // its state rather than a stack of empty controls.
  const [panel, setPanel] = useState(null)
  const [leadId, setLeadId] = useState(task.lead?.id ? String(task.lead.id) : '')
  const [note, setNote] = useState('')
  const [safetyChecked, setSafetyChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function update(payload, success) {
    setBusy(true)
    setError(null)
    try {
      await api.updateTask(task.id, payload)
      setNote('')
      setSafetyChecked(false)
      setPanel(null)
      await onChanged(success)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  function toggle(name) {
    setError(null)
    // Reopening starts from what the board currently says, so an abandoned
    // edit cannot be saved later by accident.
    if (name === 'assign') setLeadId(task.lead?.id ? String(task.lead.id) : '')
    if (name === 'note') setNote('')
    if (name === 'safety') setSafetyChecked(false)
    setPanel((open) => (open === name ? null : name))
  }

  // A case waiting on the resident, or closed by them, is read-only here.
  const locked = ['pending_confirm', 'closed'].includes(task.case_status)
  const done = task.status === 'done'
  const updates = task.updates || []
  const lastUpdate = updates.at(-1)
  const leadChanged = String(task.lead?.id || '') !== leadId
  const isLead = task.lead?.id === currentUserId

  return (
    <article className={`task-card${done ? ' task-card--done' : ''}`}>
      <div className="task-card__head">
        <span className="task-card__ref">
          {TYPE_PATHS[task.task_type] && <Icon path={TYPE_PATHS[task.task_type]} />}
          #{task.case_reference}
        </span>
        {task.case_score_total != null && (
          <span
            className={scoreClass(task.case_priority_band)}
            title={`Case priority ${task.case_score_total} (${task.case_priority_band})`}
          >
            {task.case_score_total}
          </span>
        )}
      </div>

      <div>
        <h3 className="title">{task.title}</h3>
        <p className="meta">
          {task.task_type_display} · {task.case_village}
        </p>
      </div>

      {task.safety_note && (
        <div className="task-card__safety">
          <div className="task-card__safety-title"><Icon path={PATHS.warn} /> Safety note</div>
          <p>{task.safety_note}</p>
          {task.safety_acknowledgement && (
            <p className="task-card__safety-ack">
              Acknowledged by {task.safety_acknowledgement.by} ·{' '}
              {new Date(task.safety_acknowledgement.at).toLocaleString()}
            </p>
          )}
        </div>
      )}

      {lastUpdate && (
        <p className="task-card__note">
          {lastUpdate.detail}
          <span className="who">
            — {lastUpdate.actor || 'the team'}
            {updates.length > 1 ? ` · ${updates.length} notes` : ''}
          </span>
        </p>
      )}

      <div className="task-card__lead">
        {task.lead ? (
          <>
            <span className="avatar avatar--sm" aria-hidden="true">
              {initials(task.lead.full_name)}
            </span>
            <span className="name">{task.lead.full_name}</span>
          </>
        ) : (
          <>
            <span className="avatar avatar--sm avatar--grey" aria-hidden="true">
              ·
            </span>
            <span className="name text-muted">No responder assigned</span>
          </>
        )}
        <span className={`badge ${STATUS_BADGE[task.status] || 'badge--new'}`}>
          {task.status_display}
        </span>
      </div>

      {locked ? (
        <p className="meta">
          {task.case_status === 'pending_confirm'
            ? 'Waiting for the resident to confirm the work.'
            : 'The resident confirmed this case. It is closed.'}
        </p>
      ) : (
        <div className="task-card__actions">
          {!done && (
            <button
              className="btn btn--ghost btn--sm"
              aria-expanded={panel === 'assign'}
              onClick={() => toggle('assign')}
            >
              {task.lead ? 'Reassign' : 'Assign responder'}
            </button>
          )}
          {task.status === 'assigned' && isLead && (
            <button
              className="btn btn--secondary btn--sm"
              disabled={busy}
              aria-expanded={task.safety_note ? panel === 'safety' : undefined}
              onClick={() => task.safety_note
                ? toggle('safety')
                : update({ status: 'in_progress' }, 'Work started.')}
            >
              Start work
            </button>
          )}
          {task.status === 'assigned' && !isLead && (
            <span className="meta">Waiting for {task.lead?.full_name || 'a lead'} to start</span>
          )}
          {task.status === 'in_progress' && (
            <>
              <button
                className="btn btn--ghost btn--sm"
                aria-expanded={panel === 'note'}
                onClick={() => toggle('note')}
              >
                Add progress note
              </button>
              <button
                className="btn btn--secondary btn--sm"
                disabled={busy}
                onClick={() => update({ status: 'done' }, 'Task marked done.')}
              >
                Mark done
              </button>
            </>
          )}
          {done && task.case_status === 'in_progress' && (
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => update({ status: 'in_progress' }, 'Task reopened for follow-up.')}
            >
              Reopen for follow-up
            </button>
          )}
        </div>
      )}

      {panel === 'assign' && !locked && (
        <div className="task-card__panel">
          <div className="field">
            <label htmlFor={`lead-${task.id}`}>Accountable responder</label>
            <select
              id={`lead-${task.id}`}
              className="input"
              value={leadId}
              disabled={busy}
              onChange={(event) => setLeadId(event.target.value)}
            >
              {task.status !== 'in_progress' && <option value="">Unassigned</option>}
              {responders.map((responder) => (
                <option key={responder.id} value={responder.id}>
                  {responder.full_name}
                </option>
              ))}
            </select>
            <p className="help">
              {task.status === 'in_progress'
                ? 'Reassigning returns this task to Assigned; the new lead must start it.'
                : 'One person answers for this task; the change is logged.'}
            </p>
          </div>
          <div className="row" style={{ gap: '0.8rem' }}>
            <button
              className="btn btn--primary btn--sm"
              disabled={busy || !leadChanged}
              onClick={() =>
                update(
                  { lead_user_id: leadId ? Number(leadId) : null },
                  'Task assignment updated.',
                )
              }
            >
              {busy ? 'Saving…' : 'Save responder'}
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {panel === 'safety' && !locked && isLead && task.status === 'assigned' && (
        <div className="task-card__panel">
          <div className="task-card__safety">
            <div className="task-card__safety-title"><Icon path={PATHS.warn} /> Safety note</div>
            <p>{task.safety_note}</p>
          </div>
          <label className="text-sm">
            <input
              type="checkbox"
              checked={safetyChecked}
              onChange={(event) => setSafetyChecked(event.target.checked)}
            />{' '}
            I have read this safety note and will follow it. This records that the warning was
            shown to me; it does not confirm the site is safe.
          </label>
          <div className="row" style={{ gap: '0.8rem' }}>
            <button
              className="btn btn--primary btn--sm"
              disabled={busy || !safetyChecked}
              onClick={() => update({ status: 'in_progress', safety_acknowledged: true }, 'Work started.')}
            >
              {busy ? 'Starting…' : 'Start work'}
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>Cancel</button>
          </div>
        </div>
      )}

      {panel === 'note' && !locked && (
        <div className="task-card__panel">
          {updates.length > 0 && (
            <div className="task-card__notes">
              {updates.map((update_, index) => (
                <p className="meta" key={`${update_.created_at}-${index}`}>
                  <span className="text-strong">{update_.actor || 'The team'}</span> ·{' '}
                  {update_.detail}
                </p>
              ))}
            </div>
          )}
          <div className="field">
            <label htmlFor={`note-${task.id}`}>Add a progress note</label>
            <textarea
              id={`note-${task.id}`}
              className="input"
              rows="2"
              maxLength="1000"
              placeholder="What changed on site?"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
            <p className="help">Notes are added, never edited, and stamped with who wrote them.</p>
          </div>
          <div className="row" style={{ gap: '0.8rem' }}>
            <button
              className="btn btn--primary btn--sm"
              disabled={busy || !note.trim()}
              onClick={() => update({ note }, 'Progress note recorded.')}
            >
              {busy ? 'Saving…' : 'Post note'}
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setPanel(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="meta" style={{ color: 'var(--danger-600)' }}>
          {error}
        </p>
      )}
    </article>
  )
}

export default function TaskBoard({ user, onLogout, onNavigate }) {
  useDocumentTitle('Task board')
  const [board, setBoard] = useState({ tasks: [], cases: [], responders: [] })
  const [loading, setLoading] = useState(true)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [error, setError] = useState(null)
  const [boardLoadError, setBoardLoadError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ caseId: '', title: '', taskType: 'cleanup', leadId: '', safetyNote: '' })
  const [releaseCaseId, setReleaseCaseId] = useState(null)
  const [releaseReason, setReleaseReason] = useState('')
  const [releasing, setReleasing] = useState(false)
  const [completingId, setCompletingId] = useState(null)
  const [unread, setUnread] = useState(0)

  async function loadBoard() {
    const data = await api.taskBoard()
    setBoard(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    api.notifications().then((data) => { if (!cancelled) setUnread(data.unread) }).catch(() => {})
    api.taskBoard()
      .then((data) => {
        if (cancelled) return
        setBoard(data)
        setForm((current) => ({
          ...current,
          caseId: current.caseId || String(data.cases.find((item) => item.status !== 'pending_confirm')?.id || ''),
          leadId: current.leadId || String(user.id),
        }))
      })
      .catch((err) => !cancelled && setBoardLoadError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [user.id, loadAttempt])

  async function refresh(message) {
    try {
      await loadBoard()
      setNotice(message)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function createTask(event) {
    event.preventDefault()
    setCreating(true)
    setError(null)
    try {
      await api.createTask(Number(form.caseId), {
        title: form.title,
        task_type: form.taskType,
        lead_user_id: form.leadId ? Number(form.leadId) : null,
        safety_note: form.safetyNote,
      })
      setForm((current) => ({ ...current, title: '', safetyNote: '' }))
      setShowCreate(false)
      await refresh('Task created and added to the audit trail.')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setCreating(false)
    }
  }

  async function requestCompletion(caseId) {
    setCompletingId(caseId)
    setError(null)
    try {
      await api.completeCase(caseId)
      await refresh('The resident has been asked to confirm completion.')
    } catch (err) {
      setError(err.message)
    } finally {
      setCompletingId(null)
    }
  }

  async function releaseClaim(caseId) {
    setReleasing(true)
    setError(null)
    try {
      await api.releaseCase(caseId, releaseReason)
      setReleaseCaseId(null)
      setReleaseReason('')
      await refresh('The case was released to the verified queue.')
    } catch (err) {
      setError(err.message)
    } finally {
      setReleasing(false)
    }
  }

  const columns = useMemo(
    () => ({
      todo: board.tasks.filter((task) => ['open', 'assigned'].includes(task.status)),
      inProgress: board.tasks.filter((task) => task.status === 'in_progress'),
      done: board.tasks.filter((task) => task.status === 'done'),
    }),
    [board.tasks],
  )

  const tasksByCase = useMemo(() => {
    const grouped = new Map()
    board.tasks.forEach((task) => {
      if (!grouped.has(task.case_id)) grouped.set(task.case_id, [])
      grouped.get(task.case_id).push(task)
    })
    return grouped
  }, [board.tasks])

  // Two cases need a decision from the team: the one claimed with nothing on
  // the board, and the one whose tasks are all finished.
  const unstartedCases = board.cases.filter(
    (item) => item.status === 'claimed' && !tasksByCase.has(item.id),
  )
  const completionCases = board.cases.filter((item) => {
    const tasks = tasksByCase.get(item.id) || []
    return (
      ['claimed', 'in_progress'].includes(item.status) &&
      tasks.length > 0 &&
      tasks.every((task) => task.status === 'done')
    )
  })
  const activeCases = board.cases.filter((item) => item.status !== 'pending_confirm')
  const releaseCase = unstartedCases.find((item) => item.id === releaseCaseId)

  const userInitials = initials(user.full_name)

  const boardColumns = [
    {
      key: 'todo',
      label: 'To do',
      modifier: '',
      tasks: columns.todo,
      empty: 'Nothing waiting to start.',
    },
    {
      key: 'in-progress',
      label: 'In progress',
      modifier: ' board-col--progress',
      tasks: columns.inProgress,
      empty: 'No task is under way.',
    },
    {
      key: 'done',
      label: 'Done this week',
      modifier: ' board-col--done',
      tasks: columns.done,
      empty: null,
    },
  ]

  return (
    <div className="app">
      <aside className="sidebar">
        <a className="logo" href="#queue" onClick={(event) => { event.preventDefault(); onNavigate('queue') }}>
          <span className="logo__mark"><Icon path={PATHS.logo} /></span>
          <span>
            <span className="logo__name">HighGround</span><br />
            <span className="logo__role">NGO responder</span>
          </span>
        </a>
        <nav className="side-nav">
          <a href="#queue" onClick={(event) => { event.preventDefault(); onNavigate('queue') }}>
            <Icon path={PATHS.queue} /> Case queue
          </a>
          <a href="#tasks" className="active" aria-current="page" onClick={(event) => event.preventDefault()}>
            <Icon path={PATHS.tasks} /> Task board
            {board.tasks.length > 0 && <span className="side-nav__count">{board.tasks.length}</span>}
          </a>
          <a href="#notifications" onClick={(event) => { event.preventDefault(); onNavigate('notifications') }}>
            <Icon path={PATHS.bell} /> Notifications
            {unread > 0 && <span className="side-nav__count">{unread}</span>}
          </a>
          <a href="#rules" onClick={(event) => { event.preventDefault(); onNavigate('rules') }}>
            <Icon path={PATHS.rules} /> How scoring works
          </a>
          <span className="side-nav__label">Organisation</span>
          <span className="side-nav__item side-nav__item--static">
            <Icon path={PATHS.org} /> {user.organization || 'No organisation'}
          </span>
        </nav>
        <div className="sidebar__user">
          <span className="avatar avatar--info">{userInitials}</span>
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

      <main className="main main--vp">
        <div className="page-header">
          <div>
            <h1>Task board</h1>
            <p>
              {board.tasks.length} {board.tasks.length === 1 ? 'task' : 'tasks'} across{' '}
              {tasksByCase.size} {tasksByCase.size === 1 ? 'case' : 'cases'} · one accountable
              responder per task, progress recorded as timestamped notes.
            </p>
          </div>
          <button
            className="btn btn--primary"
            disabled={activeCases.length === 0}
            title={activeCases.length === 0 ? 'Claim a case before adding tasks to it.' : undefined}
            aria-expanded={showCreate}
            onClick={() => setShowCreate((shown) => !shown)}
          >
            + Add task
          </button>
        </div>

        {notice && (
          <div className="banner banner--info" style={{ marginBottom: 'var(--sp-12)' }}>
            <Icon path={PATHS.check} />
            <span className="body">{notice}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="banner banner--danger" style={{ marginBottom: 'var(--sp-12)' }}>
            <Icon path={PATHS.warn} />
            <span className="body">{error}</span>
          </div>
        )}

        {showCreate && (
          <form className="panel" onSubmit={createTask} style={{ marginBottom: 'var(--sp-12)' }}>
            <div className="panel__header">
              <h4>New task</h4>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowCreate(false)}>
                Close
              </button>
            </div>
            <div className="panel__grid">
              <div className="field">
                <label htmlFor="task-case">Claimed case</label>
                <select id="task-case" className="input" required value={form.caseId} onChange={(event) => setForm({ ...form, caseId: event.target.value })}>
                  <option value="">Choose a case</option>
                  {activeCases.map((item) => <option key={item.id} value={item.id}>#{item.reference} · {item.village}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="task-title">Task</label>
                <input id="task-title" className="input" required maxLength="150" placeholder="e.g. Remove damaged furniture" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="task-type">Type</label>
                <select id="task-type" className="input" value={form.taskType} onChange={(event) => setForm({ ...form, taskType: event.target.value })}>
                  {TASK_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="task-lead">Accountable responder</label>
                <select id="task-lead" className="input" value={form.leadId} onChange={(event) => setForm({ ...form, leadId: event.target.value })}>
                  <option value="">Assign later</option>
                  {board.responders.map((responder) => <option key={responder.id} value={responder.id}>{responder.full_name}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="task-safety-note">Safety note (optional)</label>
              <textarea
                id="task-safety-note"
                className="input"
                rows="2"
                maxLength="500"
                value={form.safetyNote}
                onChange={(event) => setForm({ ...form, safetyNote: event.target.value })}
              />
              <p className="help">Record site hazards only. Do not include medical or personal details.</p>
            </div>
            <div className="row" style={{ gap: '0.8rem' }}>
              <button className="btn btn--primary btn--sm" disabled={creating}>{creating ? 'Creating…' : 'Create task'}</button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowCreate(false)}>Cancel</button>
            </div>
          </form>
        )}

        {(unstartedCases.length > 0 || completionCases.length > 0) && (
          <div className="stack" style={{ gap: '0.8rem', marginBottom: 'var(--sp-12)' }}>
            {unstartedCases.map((item) => (
              <div key={`unstarted-${item.id}`} className="case-strip">
                {item.score_total != null && (
                  <span className={scoreClass(item.priority_band)}>{item.score_total}</span>
                )}
                <div className="case-strip__body">
                  <div className="nm">#{item.reference} · {item.village}</div>
                  <div className="sk">
                    Claimed, with nothing on the board yet. Add the first task, or release the case
                    back to the verified queue.
                  </div>
                </div>
                <div className="case-strip__actions">
                  <button
                    className="btn btn--ghost btn--sm"
                    aria-expanded={releaseCaseId === item.id}
                    onClick={() => {
                      setReleaseCaseId((current) => (current === item.id ? null : item.id))
                      setReleaseReason('')
                    }}
                  >
                    Release case
                  </button>
                </div>
              </div>
            ))}
            {completionCases.map((item) => (
              <div key={`complete-${item.id}`} className="case-strip">
                {item.score_total != null && (
                  <span className={scoreClass(item.priority_band)}>{item.score_total}</span>
                )}
                <div className="case-strip__body">
                  <div className="nm">#{item.reference} · {item.village}</div>
                  <div className="sk">
                    Every task is done. The resident confirms before the case closes.
                  </div>
                </div>
                <div className="case-strip__actions">
                  <button
                    className="btn btn--primary btn--sm"
                    disabled={completingId === item.id}
                    onClick={() => requestCompletion(item.id)}
                  >
                    {completingId === item.id ? 'Asking…' : 'Request resident confirmation'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {releaseCase && (
          <div className="panel panel--narrow" style={{ marginBottom: 'var(--sp-12)' }}>
            <div className="panel__header">
              <h4>Release #{releaseCase.reference} back to the verified queue</h4>
              <button className="btn btn--ghost btn--sm" onClick={() => setReleaseCaseId(null)}>
                Close
              </button>
            </div>
            <p className="text-sm text-muted">
              Giving a case back is a normal outcome, not a failure — the wrong equipment, no
              access, or another organisation already on site. The reason goes into the case's
              event log, so whoever claims it next is not starting blind.
            </p>
            <div className="field">
              <label htmlFor="release-reason">
                Reason for releasing <span className="required">*</span>
              </label>
              <textarea
                id="release-reason"
                className="input"
                rows="2"
                maxLength="500"
                placeholder="e.g. Outside our working area — no crew within reach this week."
                value={releaseReason}
                onChange={(event) => setReleaseReason(event.target.value)}
              />
            </div>
            <div className="row" style={{ gap: '0.8rem' }}>
              <button
                className="btn btn--primary btn--sm"
                disabled={releasing || !releaseReason.trim()}
                onClick={() => releaseClaim(releaseCase.id)}
              >
                {releasing ? 'Releasing…' : 'Release case'}
              </button>
              <button className="btn btn--ghost btn--sm" onClick={() => setReleaseCaseId(null)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-muted">Loading task board…</p>
        ) : boardLoadError ? (
          <p role="alert" className="text-sm">Could not load the task board: {boardLoadError} <button className="btn btn--ghost btn--sm" onClick={() => { setBoardLoadError(null); setLoading(true); setLoadAttempt((n) => n + 1) }}>Retry</button></p>
        ) : (
          <div className="board vp-fill">
            {boardColumns.map((column) => (
              <section className={`board-col${column.modifier}`} key={column.key}>
                <h2 className="board-col__header">
                  {column.label} <span className="board-col__count">{column.tasks.length}</span>
                </h2>
                {column.tasks.map((task) => (
                  <TaskCard key={task.id} task={task} responders={board.responders} currentUserId={user.id} onChanged={refresh} />
                ))}
                {column.tasks.length === 0 && column.empty && (
                  <p className="board-col__empty">{column.empty}</p>
                )}
                {column.key === 'done' && column.tasks.length === 0 && (
                  <div className="board-col__rest">
                    <span className="spot-illus spot-illus--sm" aria-hidden="true">
                      <svg viewBox="0 0 96 72" fill="none">
                        <rect x="24" y="34" width="48" height="28" rx="3" fill="#D9F1F2" stroke="#D6D0C8" strokeWidth="2" />
                        <path d="M24 42 H72" stroke="#D6D0C8" strokeWidth="2" />
                        <path d="M40 34 L48 22 L56 34" stroke="#D6D0C8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M40 50 L46 56 L58 44" stroke="#1B7179" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                    <span className="text-sm text-strong">All caught up</span>
                    <span className="text-xs text-muted">Tasks marked done appear here.</span>
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
