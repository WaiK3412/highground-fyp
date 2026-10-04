import { useState } from 'react'
import { api } from '../../api'
import CaseFacts from '../CaseFacts'
import CaseTimeline from '../../pages/CaseTimeline'
import { PriorityChip } from './CaseCard'
import CaseActions from './CaseActions'

// FR23: class changes need an officer's reason visible to the household; statuses are server-enforced.
const OVERRIDABLE = new Set(['verified', 'claimed', 'in_progress', 'pending_confirm'])

function OverrideForm({ detail, onDone }) {
  const [open, setOpen] = useState(false)
  const [priorityClass, setPriorityClass] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!open) {
    return (
      <button className="btn btn--ghost btn--sm" style={{ marginTop: '1rem' }} onClick={() => setOpen(true)}>
        Change class
      </button>
    )
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.overridePriority(detail.id, Number(priorityClass), reason)
      setOpen(false)
      await onDone()
    } catch (err) {
      setError(err.fields ? Object.values(err.fields).flat().join(' ') : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: '0.8rem', marginTop: '1rem' }} onSubmit={submit}>
      <div className="field">
        <label htmlFor="override-class">New class</label>
        <select id="override-class" className="input" value={priorityClass} onChange={(e) => setPriorityClass(e.target.value)} required>
          <option value="">Choose a class</option>
          {[1, 2, 3].filter((c) => c !== detail.priority_class).map((c) => (
            <option key={c} value={c}>{c} — {{ 1: 'Health-critical', 2: 'At risk', 3: 'Standard' }[c]}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="override-reason">Reason (the household will see this)</label>
        <input id="override-reason" className="input" maxLength="500" value={reason} onChange={(e) => setReason(e.target.value)} required />
      </div>
      <div className="row gap-8">
        <button className="btn btn--primary btn--sm" disabled={busy || !reason.trim()}>{busy ? 'Saving…' : 'Save class'}</button>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </form>
  )
}

/** classes-1.0: vulnerability reasons belong to full detail; NGO summaries show only the class. */
function PriorityPanel({ detail, user, onDone }) {
  if (detail.priority_class == null) {
    return (
      <p className="text-sm text-muted mt-16">
        Not yet classified — priority is assigned when an officer verifies the request.
      </p>
    )
  }
  const reasons = detail.priority_reasons || []
  return (
    <section className="mt-16" aria-label="Priority">
      <div className="row--between">
        <span className="text-strong">Priority</span>
        <span className="row gap-8">
          <strong>{detail.priority_label}</strong>
          <PriorityChip item={detail} />
        </span>
      </div>
      {reasons.length > 0 && (
        <ul className="text-sm" style={{ margin: 'var(--sp-12) 0 0', paddingLeft: '1.6rem' }}>
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <hr className="divider" style={{ margin: '1.2rem 0' }} />
      <span className="text-xs text-muted">
        Cases are served by class, then in the order they were submitted (classes-1.0).
      </span>
      {user?.role === 'disaster_officer' && OVERRIDABLE.has(detail.status) && onDone && (
        <OverrideForm key={detail.id} detail={detail} onDone={onDone} />
      )}
    </section>
  )
}

export default function CasePanel({ detail, onClose, user, onDone, onOpenDuplicate }) {
  if (!detail) return null
  const summaryOnly = detail.detail_access === 'summary'
  return (
    <aside className="card">
      <div className="row--between">
        <h2 className="panel-title">#{detail.reference}</h2>
        <button className="btn btn--ghost btn--sm" onClick={onClose}>
          Close
        </button>
      </div>

      {summaryOnly ? (
        <div className="banner banner--info" style={{ marginTop: 'var(--sp-12)' }}>
          <span className="body">
            <span className="title">Household details are protected.</span>
            <br />
            This coordination summary is enough to assess capacity. Photos, vulnerability details,
            case history and the exact address are released only to the claiming organisation.
          </span>
        </div>
      ) : (
        <p className="text-sm text-muted" style={{ marginTop: 'var(--sp-8)' }}>
          {detail.description}
        </p>
      )}

      {/* private_files.py permission-checks photo URLs so private evidence never becomes public media. */}
      {!summaryOnly && detail.photos?.length > 0 && (
        <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', marginTop: 'var(--sp-12)' }}>
          {detail.photos.map((photo, index) => (
            <a key={photo.url} href={photo.url} target="_blank" rel="noreferrer">
              <img
                src={photo.url}
                alt={photo.caption || `${photo.stage_display} photo ${index + 1} for #${detail.reference}`}
                loading="lazy"
                style={{ width: '9.6rem', height: '7.2rem', objectFit: 'cover', borderRadius: 'var(--radius-sm)' }}
              />
              <span className="text-xs block">{photo.stage_display}</span>
            </a>
          ))}
        </div>
      )}

      {/* Officers verify from the household's own answers. */}
      {!summaryOnly && (
        <section className="mt-16" aria-label="Household answers">
          <CaseFacts detail={detail} />
        </section>
      )}

      <PriorityPanel detail={detail} user={user} onDone={onDone} />

      {user.role === 'disaster_officer' && detail.duplicate_review?.open_match_ids?.length > 0 && (
        <div className="row" style={{ flexWrap: 'wrap', marginTop: 'var(--sp-12)' }}>
          <span className="badge badge--duplicate">Possible duplicate</span>
          {detail.duplicate_review.open_match_ids.map((id) => (
            <button key={id} className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(id, detail.id)}>
              Review pair #{id}
            </button>
          ))}
        </div>
      )}
      {user.role === 'disaster_officer' && detail.duplicate_review?.confirmed_match_id && (
        <button className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(detail.duplicate_review.confirmed_match_id, detail.id)}>
          Open confirmed duplicate review
        </button>
      )}

      <div className="mt-16">
        <span className="text-xs text-muted">
          {detail.location.precision === 'exact' ? 'Exact location' : 'Approximate location'}
        </span>
        <div className="text-sm">{detail.location.address}</div>
        {detail.location.precision === 'village' && (
          <div className="text-xs text-muted" style={{ marginTop: '0.4rem' }}>
            Exact coordinates are released to the district office and the claiming organisation only.
          </div>
        )}
      </div>

      {/* Includes the household's replies to "Ask for more". */}
      {!summaryOnly && (
        <div className="mt-16">
          <CaseTimeline events={detail.events} plainTitles={false} />
        </div>
      )}

      <CaseActions detail={detail} user={user} onDone={onDone} onOpenDuplicate={onOpenDuplicate} />
    </aside>
  )
}
