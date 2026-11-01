import { useState } from 'react'
import { api } from '../../api'
import { Icon, PATHS, TASK_TYPE_PATHS } from '../../icons'
import { MAX_PHOTOS, MAX_PHOTO_BYTES, priorityChipClass, errorText } from './taskHelpers'
import { AssignmentPanel, SafetyPanel, ProgressPanel } from './TaskPanels'
import { initials } from '../../initials'

// The task's own state, in the badge vocabulary the rest of the app uses.
const STATUS_BADGE = {
  open: 'badge--new',
  assigned: 'badge--assigned',
  in_progress: 'badge--progress',
  done: 'badge--resolved',
}

export default function TaskCard({ task, responders, currentUserId, onChanged }) {
  // Open one panel at a time so a resting card stays focused on its state.
  const [panel, setPanel] = useState(null)
  const [leadId, setLeadId] = useState(task.lead?.id ? String(task.lead.id) : '')
  const [note, setNote] = useState('')
  const [shareNote, setShareNote] = useState(false)
  const [photos, setPhotos] = useState([])
  const [photoStage, setPhotoStage] = useState('before')
  const [caption, setCaption] = useState('')
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

  async function postProgress() {
    setBusy(true)
    setError(null)
    let noteSaved = false
    let photosSaved = false
    try {
      if (note.trim()) {
        await api.updateTask(task.id, shareNote ? { note, share_with_household: true } : { note })
        noteSaved = true
        setNote('')
        setShareNote(false)
      }
      if (photos.length) {
        await api.addTaskPhotos(task.id, photoStage, photos, caption)
        photosSaved = true
        setPhotos([])
        setCaption('')
      }
      setPanel(null)
      await onChanged(noteSaved && photosSaved ? 'Progress note and photos recorded.' : photosSaved ? 'Photos added.' : 'Progress note recorded.')
    } catch (err) {
      // Clear saved notes after partial success so photo retries cannot duplicate them; report the failure.
      setError(noteSaved && !photosSaved && photos.length
        ? `The note was saved, but the photos were not uploaded. ${errorText(err)}`
        : errorText(err))
      if (noteSaved || photosSaved) await onChanged()
    } finally {
      setBusy(false)
    }
  }

  function pickPhotos(event) {
    const selected = Array.from(event.target.files || [])
    const message = selected.length > MAX_PHOTOS
      ? `Choose at most ${MAX_PHOTOS} photos.`
      : selected.some((photo) => photo.size > MAX_PHOTO_BYTES)
        ? 'Each photo must be 5 MB or smaller.'
        : null
    setError(message)
    setPhotos(message ? [] : selected)
    if (message) event.target.value = ''
  }

  function toggle(name) {
    setError(null)
    // Reset abandoned edits from the current board before reopening a panel.
    if (name === 'assign') setLeadId(task.lead?.id ? String(task.lead.id) : '')
    if (name === 'note') {
      setNote('')
      setPhotos([])
      setCaption('')
      setPhotoStage(['open', 'assigned'].includes(task.status) ? 'before' : 'after')
    }
    if (name === 'safety') setSafetyChecked(false)
    setPanel((open) => (open === name ? null : name))
  }

  // Another organisation's pending job must not freeze this team's work.
  const locked = !['claimed', 'in_progress'].includes(task.job_status)
  const done = task.status === 'done'
  const updates = task.updates || []
  const lastUpdate = updates.at(-1)
  const leadChanged = String(task.lead?.id || '') !== leadId
  const isLead = task.lead?.id === currentUserId

  return (
    <article className={`task-card${done ? ' task-card--done' : ''}`}>
      <div className="task-card__head">
        <span className="task-card__ref">
          {TASK_TYPE_PATHS[task.task_type] && <Icon path={TASK_TYPE_PATHS[task.task_type]} />}
          #{task.case_reference}
        </span>
        {task.case_priority_class != null && (
          <span
            className={priorityChipClass(task.case_priority_class)}
            title={`Priority class ${task.case_priority_class}: ${task.case_priority_label}`}
            aria-label={`Priority class ${task.case_priority_class}: ${task.case_priority_label}`}
          >
            {task.case_priority_class}
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
          <div className="task-card__safety-title"><Icon path={PATHS.warning} /> Safety note</div>
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
            {updates.length > 1 ? ` · ${updates.length} updates` : ''}
          </span>
        </p>
      )}

      {task.photos?.length > 0 && (
        <div className="row wrap gap-8">
          {task.photos.map((photo) => (
            <a key={photo.url} href={photo.url} target="_blank" rel="noreferrer">
              <img src={photo.url} alt={photo.caption || `${photo.stage_display} photo of ${task.title}`} loading="lazy"
                style={{ width: '7.2rem', height: '5.4rem', objectFit: 'cover', borderRadius: 'var(--radius-sm)' }} />
              <span className="text-xs block">{photo.stage_display}</span>
            </a>
          ))}
        </div>
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
          {task.job_status === 'pending_confirm'
            ? 'Waiting for the resident to confirm the work.'
            : task.job_status === 'closed_unconfirmed'
              ? 'This job was closed without household confirmation.'
              : 'This job is finished and closed to changes.'}
        </p>
      ) : (
        <div className="task-card__actions">
          {!done && (
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
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
          <button className="btn btn--ghost btn--sm" disabled={busy} aria-expanded={panel === 'note'} onClick={() => toggle('note')}>
            Add progress note
          </button>
          {task.status === 'in_progress' && (
            <>
              <button
                className="btn btn--secondary btn--sm"
                disabled={busy}
                onClick={() => update({ status: 'done' }, 'Task marked done.')}
              >
                Mark done
              </button>
            </>
          )}
          {done && task.job_status === 'in_progress' && (
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
        <AssignmentPanel
          task={task} responders={responders} leadId={leadId} setLeadId={setLeadId}
          busy={busy} leadChanged={leadChanged} update={update} setPanel={setPanel}
        />
      )}

      {panel === 'safety' && !locked && isLead && task.status === 'assigned' && (
        <SafetyPanel
          task={task} safetyChecked={safetyChecked} setSafetyChecked={setSafetyChecked}
          busy={busy} update={update} setPanel={setPanel}
        />
      )}

      {panel === 'note' && !locked && (
        <ProgressPanel
          task={task} updates={updates} note={note} setNote={setNote}
          shareNote={shareNote} setShareNote={setShareNote}
          photoStage={photoStage} setPhotoStage={setPhotoStage} photos={photos}
          caption={caption} setCaption={setCaption} busy={busy}
          pickPhotos={pickPhotos} postProgress={postProgress} setPanel={setPanel}
        />
      )}

      {error && (
        <p role="alert" className="meta text-danger">
          {error}
        </p>
      )}
    </article>
  )
}
