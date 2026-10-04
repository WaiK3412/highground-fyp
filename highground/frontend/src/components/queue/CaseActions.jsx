import { useState } from 'react'
import { api } from '../../api'
import { openJobsFor, confirmationDays } from './caseHelpers'

export default function CaseActions({ detail, user, onDone, onOpenDuplicate }) {
  const [busy, setBusy] = useState(false)
  const [claimingId, setClaimingId] = useState(null)
  const [error, setError] = useState(null)
  const [note, setNote] = useState('')
  const [closeOutcome, setCloseOutcome] = useState('')
  const [closeNote, setCloseNote] = useState('')

  const openJobs = openJobsFor(user, detail)
  const canClaim = openJobs.length > 0
  const canDecide = user.role === 'disaster_officer' && detail.status === 'submitted'
  const canClose = user.role === 'disaster_officer' && detail.status === 'pending_confirm'
  const unfinishedHelp = (detail.jobs || []).some((job) =>
    !['pending_confirm', 'done', 'closed_unconfirmed'].includes(job.status),
  )

  if (!canClaim && !canDecide && !canClose) return null

  async function run(action) {
    setError(null)
    setBusy(true)
    try {
      await action()
      await onDone()
    } catch (err) {
      setError({
        message: err.fields ? Object.values(err.fields).flat().join(' ') : err.message,
        code: err.code,
        matchIds: err.data?.duplicate_match_ids || [],
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 'var(--sp-16)', borderTop: '1px solid var(--grey-200)', paddingTop: 'var(--sp-16)' }}>
      {error && (
        <div
          role="alert"
          style={{
            background: 'var(--danger-100)',
            color: 'var(--danger-600)',
            padding: '0.8rem 1rem',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--fs-12)',
            fontWeight: 600,
            marginBottom: 'var(--sp-12)',
          }}
        >
          {error.code === 'duplicate_check_pending'
            ? 'The duplicate check has not finished. Refresh this case before trying to verify it.'
            : error.code === 'duplicate_review_required'
              ? 'A possible duplicate needs officer review before this case can be verified.'
              : error.code === 'case_linked_duplicate'
                ? 'This case was closed as a confirmed duplicate and cannot be verified again.'
                : error.message}
          {error.code === 'duplicate_check_pending' && (
            <button className="btn btn--ghost btn--sm" onClick={async () => {
              setError(null)
              try { await onDone() } catch (err) { setError({ message: err.message, matchIds: [] }) }
            }}>Refresh case</button>
          )}
          {error.matchIds.map((id) => (
            <button key={id} className="btn btn--ghost btn--sm" onClick={() => onOpenDuplicate(id, detail.id)}>
              Open duplicate review #{id}
            </button>
          ))}
        </div>
      )}

      {canClaim && (
        <div className="row wrap gap-8">
          {openJobs.map((job) => (
            <button
              key={job.id}
              className="btn btn--primary btn--sm"
              disabled={busy}
              onClick={() => {
                setClaimingId(job.id)
                run(() => api.claimJob(job.id))
              }}
            >
              {busy && claimingId === job.id ? 'Claiming…' : `Claim ${job.help_type_display.toLowerCase()}`}
            </button>
          ))}
        </div>
      )}

      {canDecide && (
        <div className="stack gap-10">
          <div className="field">
            <label htmlFor="note">Note to the household</label>
            <input
              id="note"
              className="input"
              placeholder="Required when asking for more or rejecting"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="row wrap gap-8">
            <button
              className="btn btn--primary btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'verified', note))}
            >
              Verify
            </button>
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'needs_info', note))}
            >
              Ask for more
            </button>
            <button
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => run(() => api.verifyCase(detail.id, 'rejected', note))}
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {canClose && (
        <form className="stack gap-10" onSubmit={(event) => {
          event.preventDefault()
          run(() => api.closeOnBehalf(detail.id, { outcome: closeOutcome, note: closeNote }))
        }}>
          <h3>Close without household confirmation</h3>
          <p className="text-sm text-muted">
            {detail.awaiting_confirmation_since
              ? `Waiting for the household since ${new Date(detail.awaiting_confirmation_since).toLocaleDateString()} (${confirmationDays(detail.awaiting_confirmation_since)} days)`
              : 'The date this household was asked to confirm was not recorded.'}
          </p>
          <p className="text-sm">
            This records an officer decision. The household can still report incomplete work to reopen it.
          </p>
          <div className="field">
            <label htmlFor={`close-outcome-${detail.id}`}>Outcome (required)</label>
            <select id={`close-outcome-${detail.id}`} className="input" required disabled={busy}
              value={closeOutcome} onChange={(event) => setCloseOutcome(event.target.value)}>
              <option value="">Choose an outcome</option>
              <option value="household_unreachable">Unable to contact the household</option>
              <option value="confirmed_verbally">Household confirmed by phone or in person</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`close-note-${detail.id}`}>Reason and contact attempts (required)</label>
            <textarea id={`close-note-${detail.id}`} className="input" rows="3" maxLength="500" required disabled={busy}
              placeholder="How and when did you contact the household? What completed work did you review?"
              value={closeNote} onChange={(event) => setCloseNote(event.target.value)} />
            <p className="help">The household will see this reason in the case history.</p>
          </div>
          {unfinishedHelp && (
            <p className="text-sm">Another type of help is still unfinished. Each response team must finish its work before this case can close.</p>
          )}
          <button className="btn btn--primary btn--sm" disabled={busy || unfinishedHelp || !closeOutcome || !closeNote.trim()}>
            {busy ? 'Closing…' : 'Close without household confirmation'}
          </button>
        </form>
      )}
    </div>
  )
}
