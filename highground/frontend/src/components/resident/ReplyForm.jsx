import { useState } from 'react'

const URGENCY_OPTIONS = [
  ['none', 'No safety concerns'],
  ['health_risk', 'Health concern'],
  ['medical_disrupted', 'Medical needs disrupted'],
  ['urgent', 'Someone needs urgent medical attention'],
]

const ACCESS_OPTIONS = [
  ['normal', 'Yes — normal access'],
  ['four_wd', 'Only high vehicles / 4x4'],
  ['foot', 'On foot only'],
  ['cut_off', 'Completely cut off'],
]

const VULNERABILITY_OPTIONS = [
  ['elderly', 'Elderly members (60+)'],
  ['child_under_5', 'Children under 5'],
  ['disability', 'Members with medical needs or disability'],
  ['single_parent', 'Single-parent household'],
]

export default function ReplyForm({ detail, onReply }) {
  const [note, setNote] = useState('')
  const [urgency, setUrgency] = useState(detail.urgency)
  const [access, setAccess] = useState(detail.access_level)
  const [flags, setFlags] = useState(detail.vulnerability_flags || [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const question = [...(detail.events || [])].reverse().find((e) => e.event_type === 'needs_info')

  const toggle = (flag) =>
    setFlags((current) => (current.includes(flag) ? current.filter((f) => f !== flag) : [...current, flag]))

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onReply({ note, urgency, access_level: access, vulnerability_flags: flags })
    } catch (err) {
      setError(err.fields ? Object.values(err.fields).flat().join(' ') : err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="meta-rail__section stack" style={{ gap: 'var(--sp-16)' }} onSubmit={submit}>
      <div className="banner banner--warning">
        <span className="body">
          <span className="title">The district office has asked for more information</span>
          {question?.detail && (<><br />“{question.detail}”</>)}
        </span>
      </div>
      <div className="field">
        <label htmlFor="reply-note">Your answer</label>
        <textarea id="reply-note" className="input" rows="3" maxLength="1000" value={note} onChange={(e) => setNote(e.target.value)} required />
        <span className="help">If an answer on your request was wrong, correct it below too.</span>
      </div>
      <div className="field">
        <label htmlFor="reply-urgency">Is anyone's health at risk?</label>
        <select id="reply-urgency" className="input" value={urgency} onChange={(e) => setUrgency(e.target.value)}>
          {URGENCY_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      {urgency === 'urgent' && <p className="text-sm">Call 999 first if someone needs urgent medical attention.</p>}
      <div className="field">
        <label htmlFor="reply-access">How can responders reach your home?</label>
        <select id="reply-access" className="input" value={access} onChange={(e) => setAccess(e.target.value)}>
          {ACCESS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      <fieldset className="stack gap-8" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="text-sm text-strong mb-12">Who is in your household?</legend>
        {VULNERABILITY_OPTIONS.map(([value, label]) => (
          <label key={value} className="check-row cursor-pointer">
            <input type="checkbox" checked={flags.includes(value)} onChange={() => toggle(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <button className="btn btn--primary btn--sm" style={{ alignSelf: 'flex-start' }} disabled={busy || !note.trim()}>
        {busy ? 'Sending…' : 'Send to the district office'}
      </button>
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </form>
  )
}
