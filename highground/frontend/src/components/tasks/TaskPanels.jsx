import { Icon, PATHS } from '../../icons'
import { MAX_PHOTOS } from './taskHelpers'

export function AssignmentPanel({ task, responders, leadId, setLeadId, busy, leadChanged, update, setPanel }) {
  return (
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
      <div className="row gap-8">
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
  )
}

export function SafetyPanel({ task, safetyChecked, setSafetyChecked, busy, update, setPanel }) {
  return (
    <div className="task-card__panel">
      <div className="task-card__safety">
        <div className="task-card__safety-title"><Icon path={PATHS.warning} /> Safety note</div>
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
      <div className="row gap-8">
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
  )
}

export function ProgressPanel({ task, updates, note, setNote, shareNote, setShareNote, photoStage, setPhotoStage, photos, caption, setCaption, busy, pickPhotos, postProgress, setPanel }) {
  return (
    <div className="task-card__panel">
      {updates.length > 0 && (
        <div className="task-card__notes">
          {updates.map((update_, index) => (
            <p className="meta" key={`${update_.created_at}-${index}`}>
              <span className="text-strong">{update_.actor || 'The team'}</span> ·{' '}
              {update_.shared && <span className="text-muted">Shared with the household · </span>}
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
          disabled={busy}
          onChange={(event) => setNote(event.target.value)}
        />
        <p className="help">Notes are added, never edited, and stamped with who wrote them.</p>
        <label className="text-sm">
          <input
            type="checkbox"
            checked={shareNote}
            disabled={busy}
            onChange={(event) => setShareNote(event.target.checked)}
          />{' '}
          Share this note with the household. Leave it unticked for anything only your team should read,
          such as access arrangements.
        </label>
      </div>
      <div className="field">
        <label htmlFor={`photo-stage-${task.id}`}>Photo stage</label>
        <select id={`photo-stage-${task.id}`} className="input" value={photoStage} disabled={busy} onChange={(event) => setPhotoStage(event.target.value)}>
          <option value="before">Before</option>
          <option value="after">After</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`photos-${task.id}`}>Photos (optional)</label>
        <input id={`photos-${task.id}`} type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={pickPhotos} />
        <p className="help">Up to {MAX_PHOTOS} photos, 5 MB each. You can post photos without a note.</p>
        <p className="help">Photos are private: only the household, the district office and organisations working on this request can see them. Photograph the work, not people. Ask the household before photographing inside their home; they can say no and still get help.</p>
        <p className="help">System administrators also have access to these records.</p>
      </div>
      {photos.length > 0 && (
        <div className="field">
          <label htmlFor={`photo-caption-${task.id}`}>Photo caption (optional)</label>
          <input id={`photo-caption-${task.id}`} className="input" maxLength="255" value={caption} disabled={busy} onChange={(event) => setCaption(event.target.value)} />
        </div>
      )}
      <div className="row gap-8">
        <button
          className="btn btn--primary btn--sm"
          disabled={busy || (!note.trim() && photos.length === 0)}
          onClick={postProgress}
        >
          {busy ? 'Saving…' : photos.length ? (note.trim() ? 'Post progress and photos' : 'Post photos') : 'Post note'}
        </button>
        <button className="btn btn--ghost btn--sm" disabled={busy} onClick={() => setPanel(null)}>
          Cancel
        </button>
      </div>
    </div>
  )
}
