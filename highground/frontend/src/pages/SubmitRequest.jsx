/** FR3: keep all five steps local until final review to prevent drafts or partial submissions; required village/address survive optional pin failures, and photos submit as multipart CasePhoto files. */

import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import { Icon, PATHS } from '../icons'
import ResidentShell from './ResidentShell'
import { useDocumentTitle } from '../useDocumentTitle'
import { STEPS } from '../components/request/options'
import Required from '../components/request/Required'
import StepHousehold from '../components/request/StepHousehold'
import StepDamage from '../components/request/StepDamage'
import StepNeeds from '../components/request/StepNeeds'
import StepPhotos from '../components/request/StepPhotos'
import StepReview from '../components/request/StepReview'

function Stepper({ current }) {
  return (
    <div className="card card--flat request-stepper" style={{ marginBottom: '2.4rem', padding: '1.6rem 2.4rem' }}>
      <div className="request-stepper__compact" aria-hidden="true">
        <p className="text-sm text-strong">Step {current + 1} of {STEPS.length} · {STEPS[current]}</p>
        <div className="request-stepper__track">
          <span style={{ width: `${((current + 1) / STEPS.length) * 100}%` }} />
        </div>
      </div>
      <div className="stepper" role="list" aria-label="Request steps">
        {STEPS.map((label, index) => {
          const state = index === current ? ' step--active' : index < current ? ' step--done' : ''
          return (
            <Fragment key={label}>
              <div className={`step${state}`} role="listitem" aria-current={index === current ? 'step' : undefined}>
                <span className="step__dot">{index + 1}</span>
                <span className="step__label">{label}</span>
              </div>
              {index < STEPS.length - 1 && <span className="step__line" aria-hidden="true" />}
            </Fragment>
          )
        })}
      </div>
    </div>
  )
}

// Keep required-step checks outside rendering so continuation validation is easy to inspect.
const REQUIRED_BY_STEP = [
  ['location_code', 'address'],
  ['damage_category', 'description', 'flood_depth', 'liveability', 'access_level'],
  ['urgency'],
  [],
  [],
]

export default function SubmitRequest({ user, onLogout, onSubmitted, onCancel, onNavigate }) {
  useDocumentTitle('Submit a request')

  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState({
    household_size: 1,
    location_code: '',
    pin: null,
    address: '',
    damage_category: '',
    also_need: [],
    description: '',
    flood_depth: '',
    liveability: 'liveable',
    access_level: 'normal',
    urgency: 'none',
    vulnerability_flags: [],
    needs_flags: [],
    photos: [],
  })

  const set = (patch) => setData((current) => ({ ...current, ...patch }))

  // Villages come from the controlled location table, not a list in this file.
  const [villages, setVillages] = useState({ rows: [], loading: true, error: null })
  const [villagesAttempt, setVillagesAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    api
      .locations()
      .then((rows) => !cancelled && setVillages({ rows, loading: false, error: null }))
      .catch((err) => !cancelled && setVillages({ rows: [], loading: false, error: err.message }))
    return () => {
      cancelled = true
    }
  }, [villagesAttempt])
  function retryVillages() {
    setVillages({ rows: [], loading: true, error: null })
    setVillagesAttempt((n) => n + 1)
  }

  const missing = REQUIRED_BY_STEP[step].filter((field) => {
    const value = data[field]
    return typeof value === 'string' ? value.trim() === '' : value == null
  })
  const canContinue = missing.length === 0

  async function submit() {
    setError(null)
    setBusy(true)
    try {
      await api.primeCsrf()
      // Contact fields belong to the user account; case photos travel separately as multipart rather than JSON.
      const created = await api.createCase({
        location_code: data.location_code,
        latitude: data.pin ? data.pin.latitude : null,
        longitude: data.pin ? data.pin.longitude : null,
        address: data.address,
        household_size: data.household_size,
        damage_category: data.damage_category,
        also_need: data.also_need.filter((value) => value !== data.damage_category),
        description: data.description,
        flood_depth: data.flood_depth,
        liveability: data.liveability,
        access_level: data.access_level,
        urgency: data.urgency,
        vulnerability_flags: data.vulnerability_flags,
        needs_flags: data.needs_flags,
      }, data.photos)
      onSubmitted(created)
    } catch (err) {
      // Show DRF field messages (e.g. retired villages) instead of hiding the refusal.
      setError(Object.values(err.fields || {}).flat()[0] || err.message)
      setBusy(false)
    }
  }

  return (
    <ResidentShell
      user={user} active="submit" onLogout={onLogout}
      onNavigate={(screen) => screen === 'recovery' ? onCancel() : onNavigate(screen)}
    >
        <div className="page-header">
          <div>
            <h1>Submit an aid request</h1>
            <p>
              Tell us who needs help and where to find you. Fields marked <Required /> are required.
            </p>
          </div>
        </div>

        <Stepper current={step} />

        {step === 0 && (
          <StepHousehold user={user} data={data} set={set} villages={villages} onRetryVillages={retryVillages} onNavigate={onNavigate} />
        )}
        {step === 1 && <StepDamage data={data} set={set} />}
        {step === 2 && <StepNeeds data={data} set={set} />}
        {step === 3 && <StepPhotos data={data} set={set} />}
        {step === 4 && <StepReview user={user} data={data} goTo={setStep} villages={villages} />}

        {error && (
          <div
            role="alert"
            style={{
              background: 'var(--danger-100)',
              color: 'var(--danger-600)',
              padding: '1.0rem 1.2rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--fs-14)',
              fontWeight: 600,
              marginBottom: '2.4rem',
            }}
          >
            {error}
          </div>
        )}

        <div className="row--between request-actions">
          <button className="btn btn--secondary" onClick={step === 0 ? onCancel : () => setStep(step - 1)}>
            {step === 0 ? '← Cancel' : '← Back'}
          </button>

          <div className="row" style={{ gap: '1.6rem', alignItems: 'center' }}>
            <span className="text-sm text-muted request-actions__count">
              Step {step + 1} of {STEPS.length}
            </span>
            {step < STEPS.length - 1 ? (
              <button
                className="btn btn--primary"
                onClick={() => setStep(step + 1)}
                disabled={!canContinue}
                style={canContinue ? undefined : { opacity: 0.5, cursor: 'not-allowed' }}
                title={canContinue ? undefined : 'Fill in the required fields to continue'}
              >
                Continue
                <Icon path={PATHS.arrow} strokeWidth={2} />
              </button>
            ) : (
              <button
                className="btn btn--primary"
                onClick={submit}
                disabled={busy}
                style={busy ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
              >
                {busy ? 'Submitting…' : 'Submit request'}
              </button>
            )}
          </div>
        </div>
    </ResidentShell>
  )
}
