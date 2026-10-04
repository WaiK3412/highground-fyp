import { useState } from 'react'

export default function CompletionDecision({ job, photos, onDecision }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function decide(decision) {
    setBusy(true)
    setError(null)
    try {
      await onDecision(job.id, decision, note)
    } catch (err) {
      setError(err.fields ? Object.values(err.fields).flat().join(' ') : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="meta-rail__section">
      {photos.length > 0 && (
        <div style={{ marginBottom: '1.2rem' }}>
          <h3>Photos from {job.claimed_by}</h3>
          {['before', 'after'].map((stage) => {
            const group = photos.filter((photo) => photo.stage === stage)
            if (!group.length) return null
            const label = stage === 'before' ? 'Before' : 'After'
            return (
              <div key={stage} style={{ marginTop: '0.8rem' }}>
                <p className="text-sm text-strong">{label}</p>
                <div className="row wrap gap-8">
                  {group.map((photo) => (
                    <a key={photo.url} href={photo.url} target="_blank" rel="noreferrer">
                      <img src={photo.url} alt={photo.caption || `${label} photo of the ${job.help_type_display.toLowerCase()} work`} loading="lazy"
                        style={{ width: '9.6rem', height: '7.2rem', objectFit: 'cover', borderRadius: 'var(--radius-sm)' }} />
                    </a>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="banner banner--warning">
        <span className="body">
          <span className="title">{job.status === 'closed_unconfirmed'
            ? `The district office closed the ${job.help_type_display.toLowerCase()} work without your confirmation`
            : `Is the ${job.help_type_display.toLowerCase()} work by ${job.claimed_by} complete?`}</span>
          <br />
          {job.status === 'closed_unconfirmed'
            ? 'If the work is unfinished, explain what remains. Reporting incomplete work reopens it for the response team.'
            : 'Confirm only after checking the work. If something remains, explain it so the response team has a clear follow-up record.'}
        </span>
      </div>
      <div className="field" style={{ marginTop: '1.2rem' }}>
        <label htmlFor={`completion-note-${job.id}`}>What still needs attention? (required if incomplete)</label>
        <textarea
          id={`completion-note-${job.id}`}
          className="input"
          rows="3"
          maxLength="1000"
          value={note}
          disabled={busy}
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      <div className="row" style={{ gap: '0.8rem', marginTop: '1rem', flexWrap: 'wrap' }}>
        {job.status === 'pending_confirm' && (
          <button className="btn btn--primary btn--sm" disabled={busy} onClick={() => decide('confirm')}>
            Confirm complete
          </button>
        )}
        <button
          className="btn btn--ghost btn--sm"
          disabled={busy || !note.trim()}
          onClick={() => decide('incomplete')}
        >
          Report incomplete work
        </button>
      </div>
      {error && <p role="alert" className="text-xs" style={{ color: 'var(--danger-600)', marginTop: '0.8rem' }}>{error}</p>}
    </div>
  )
}
