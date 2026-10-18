/** Screen 09 keeps the frozen v2 board layout and one accountable lead, with auditable task states and household confirmation. */

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Icon, PATHS } from '../icons'
import ResponderShell from './ResponderShell'
import { useDocumentTitle } from '../useDocumentTitle'
import TaskCard from '../components/tasks/TaskCard'
import CreateTaskForm from '../components/tasks/CreateTaskForm'
import { priorityChipClass, errorText } from '../components/tasks/taskHelpers'

export default function TaskBoard({ user, onLogout, onNavigate }) {
  useDocumentTitle('Task board')
  const [board, setBoard] = useState({ tasks: [], jobs: [], responders: [] })
  const [loading, setLoading] = useState(true)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [error, setError] = useState(null)
  const [boardLoadError, setBoardLoadError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ jobId: '', title: '', taskType: 'cleanup', leadId: '', safetyNote: '' })
  const [releaseJobId, setReleaseJobId] = useState(null)
  const [releaseReason, setReleaseReason] = useState('')
  const [releasing, setReleasing] = useState(false)
  const [completingId, setCompletingId] = useState(null)

  async function loadBoard() {
    const data = await api.taskBoard()
    setBoard(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    api.taskBoard()
      .then((data) => {
        if (cancelled) return
        setBoard(data)
        setForm((current) => ({
          ...current,
          jobId: current.jobId || String(data.jobs.find((item) => item.status !== 'pending_confirm')?.id || ''),
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
      // A task belongs to one of the organisation's jobs (ADR-020).
      const job = board.jobs.find((item) => item.id === Number(form.jobId))
      await api.createTask(job.case_id, {
        job_id: job.id,
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

  async function requestCompletion(jobId) {
    setCompletingId(jobId)
    setError(null)
    try {
      await api.completeJob(jobId)
      await refresh('The resident has been asked to confirm completion.')
    } catch (err) {
      setError(err.message)
    } finally {
      setCompletingId(null)
    }
  }

  async function releaseClaim(jobId) {
    setReleasing(true)
    setError(null)
    try {
      await api.releaseJob(jobId, releaseReason)
      setReleaseJobId(null)
      setReleaseReason('')
      await refresh('The job was released back to the queue.')
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

  // Offer team decisions for unstarted jobs and jobs whose tasks are all finished.
  const unstartedJobs = board.jobs.filter((item) => item.status === 'claimed' && item.task_count === 0)
  const completionJobs = board.jobs.filter(
    (item) =>
      ['claimed', 'in_progress'].includes(item.status) &&
      item.task_count > 0 &&
      item.tasks_done === item.task_count,
  )
  const activeJobs = board.jobs.filter((item) => item.status !== 'pending_confirm')
  const releaseJob = unstartedJobs.find((item) => item.id === releaseJobId)

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
    <ResponderShell
      user={user} active="tasks"
      counts={{ tasks: board.tasks.length > 0 ? board.tasks.length : undefined }}
      onNavigate={onNavigate} onLogout={onLogout}
      mainClassName="main main--vp" mainStyle={null}
    >
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
            disabled={activeJobs.length === 0}
            title={activeJobs.length === 0 ? 'Claim a job before adding tasks to it.' : undefined}
            aria-expanded={showCreate}
            onClick={() => setShowCreate((shown) => !shown)}
          >
            + Add task
          </button>
        </div>

        {notice && (
          <div className="banner banner--info mb-12">
            <Icon path={PATHS.check} />
            <span className="body">{notice}</span>
          </div>
        )}
        {error && (
          <div role="alert" className="banner banner--danger mb-12">
            <Icon path={PATHS.warning} />
            <span className="body">{error}</span>
          </div>
        )}

        {showCreate && (
          <CreateTaskForm createTask={createTask} setShowCreate={setShowCreate} activeJobs={activeJobs}
            form={form} setForm={setForm} board={board} creating={creating} />
        )}

        {(unstartedJobs.length > 0 || completionJobs.length > 0) && (
          <div className="stack" style={{ gap: '0.8rem', marginBottom: 'var(--sp-12)' }}>
            {unstartedJobs.map((item) => (
              <div key={`unstarted-${item.id}`} className="case-strip">
                {item.case_priority_class != null && (
                  <span
                    className={priorityChipClass(item.case_priority_class)}
                    title={item.case_priority_label}
                    aria-label={`Priority class ${item.case_priority_class}: ${item.case_priority_label}`}
                  >
                    {item.case_priority_class}
                  </span>
                )}
                <div className="case-strip__body">
                  <div className="nm">#{item.case_reference} · {item.case_village} · {item.help_type_display}</div>
                  <div className="sk">
                    Claimed, with nothing on the board yet. Add the first task, or release the job
                    back to the queue.
                  </div>
                </div>
                <div className="case-strip__actions">
                  <button
                    className="btn btn--ghost btn--sm"
                    aria-expanded={releaseJobId === item.id}
                    onClick={() => {
                      setReleaseJobId((current) => (current === item.id ? null : item.id))
                      setReleaseReason('')
                    }}
                  >
                    Release job
                  </button>
                </div>
              </div>
            ))}
            {completionJobs.map((item) => (
              <div key={`complete-${item.id}`} className="case-strip">
                {item.case_priority_class != null && (
                  <span
                    className={priorityChipClass(item.case_priority_class)}
                    title={item.case_priority_label}
                    aria-label={`Priority class ${item.case_priority_class}: ${item.case_priority_label}`}
                  >
                    {item.case_priority_class}
                  </span>
                )}
                <div className="case-strip__body">
                  <div className="nm">#{item.case_reference} · {item.case_village} · {item.help_type_display}</div>
                  <div className="sk">
                    Every task on this job is done. The resident confirms before it closes.
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

        {releaseJob && (
          <div className="panel panel--narrow mb-12">
            <div className="panel__header">
              <h4>Release the {releaseJob.help_type_display.toLowerCase()} job on #{releaseJob.case_reference}</h4>
              <button className="btn btn--ghost btn--sm" onClick={() => setReleaseJobId(null)}>
                Close
              </button>
            </div>
            <p className="text-sm text-muted">
              Giving a job back is a normal outcome, not a failure — the wrong equipment, no
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
            <div className="row gap-8">
              <button
                className="btn btn--primary btn--sm"
                disabled={releasing || !releaseReason.trim()}
                onClick={() => releaseClaim(releaseJob.id)}
              >
                {releasing ? 'Releasing…' : 'Release job'}
              </button>
              <button className="btn btn--ghost btn--sm" onClick={() => setReleaseJobId(null)}>
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
    </ResponderShell>
  )
}
