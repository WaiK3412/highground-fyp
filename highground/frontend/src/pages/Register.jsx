/**
 * Screen 03 — Create an account.
 *
 * Two paths. A resident registers outright. An organisation *applies*: it names
 * a requested_role and attaches evidence, but the account is still created as
 * community_member. Only an admin approving the application grants the role
 * (ADR-012), so nothing on this screen can hand anyone privilege.
 */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'

// system_admin is deliberately not offered, and the backend refuses it too. An
// approval flow that can mint admins is one bad click from handing over the
// platform.
const APPLICABLE_ROLES = [
  { value: 'ngo_volunteer', label: 'NGO / volunteer team member' },
  { value: 'disaster_officer', label: 'District disaster officer' },
]

function HouseIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75"
      />
    </svg>
  )
}

function BuildingIcon() {
  return (
    <svg fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.75c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
      />
    </svg>
  )
}

/**
 * Name, phone, email and password — identical on both paths, so they live in
 * one place. Only one branch is on screen at a time, so the ids cannot collide.
 */
function IdentityFields({ form, update, fieldError, errors }) {
  return (
    <>
      <div className="input-group">
        <div className="field">
          <label htmlFor="full_name">
            Full name <span className="required">*</span>
          </label>
          <input
            id="full_name"
            className="input"
            placeholder="As per MyKad"
            value={form.full_name}
            onChange={(e) => update('full_name', e.target.value)}
            required
          />
          {fieldError('full_name')}
        </div>
        <div className="field">
          <label htmlFor="phone">
            Phone number <span className="required">*</span>
          </label>
          <input
            id="phone"
            className="input"
            placeholder="+60 12-345 6789"
            value={form.phone}
            onChange={(e) => update('phone', e.target.value)}
            required
          />
          {fieldError('phone')}
        </div>
      </div>

      <div className="input-group">
        <div className="field">
          <label htmlFor="reg-email">
            Email <span className="required">*</span>
          </label>
          <input
            id="reg-email"
            className="input"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={(e) => update('email', e.target.value)}
            required
          />
          {fieldError('email')}
        </div>
        <div className="field">
          <label htmlFor="reg-password">
            Password <span className="required">*</span>
          </label>
          <input
            id="reg-password"
            className="input"
            type="password"
            placeholder="At least 8 characters"
            value={form.password}
            onChange={(e) => update('password', e.target.value)}
            required
          />
          {fieldError('password') || (
            <span className="help">Use a mix of letters and numbers.</span>
          )}
        </div>
      </div>

      <div className="input-group">
        <div className="field">
          <label htmlFor="password_confirm">
            Confirm password <span className="required">*</span>
          </label>
          <input
            id="password_confirm"
            className={`input${errors.password_confirm ? ' input--error' : ''}`}
            type="password"
            placeholder="Re-enter your password"
            value={form.password_confirm}
            onChange={(e) => update('password_confirm', e.target.value)}
            required
          />
          {fieldError('password_confirm')}
        </div>
        <div className="field" aria-hidden="true" />
      </div>
    </>
  )
}

export default function Register({ onRegistered, onShowLogin }) {
  useDocumentTitle('Create account')
  const [accountType, setAccountType] = useState('resident')
  const [organizations, setOrganizations] = useState([])
  const [requestedRole, setRequestedRole] = useState('')
  const [organizationId, setOrganizationId] = useState('')
  // e.target.files is a FileList, converted here to a real array so .map and
  // .length work below.
  const [documents, setDocuments] = useState([])

  // Load the organisation list once, when this screen first appears.
  useEffect(() => {
    api.organizations().then(setOrganizations).catch(() => setOrganizations([]))
  }, [])
  const [form, setForm] = useState({
    full_name: '',
    phone: '',
    email: '',
    password: '',
    password_confirm: '',
  })
  const [agreed, setAgreed] = useState(false)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)

  const applying = accountType === 'organisation'

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrors({})

    if (form.password !== form.password_confirm) {
      setErrors({ password_confirm: 'The two passwords do not match.' })
      return
    }

    // Re-checked on the server, which is the check that counts — this one only
    // saves the applicant a round trip.
    if (applying && documents.length === 0) {
      setErrors({ documents: 'Attach at least one supporting document.' })
      return
    }

    setBusy(true)
    try {
      await api.primeCsrf()
      // Only an application carries a role, an organisation and files; a
      // resident registration stays plain JSON.
      const payload = applying
        ? { ...form, requested_role: requestedRole, organization: organizationId }
        : form
      const user = await api.register(payload, applying ? documents : undefined)
      onRegistered(user)
    } catch (err) {
      setErrors(err.fields || { detail: err.message })
      setBusy(false)
    }
  }

  const fieldError = (name) =>
    errors[name] ? (
      <span className="help" style={{ color: 'var(--danger-600)', fontWeight: 600 }}>
        {Array.isArray(errors[name]) ? errors[name].join(' ') : errors[name]}
      </span>
    ) : null

  const errorBanner = errors.detail ? (
    <div
      role="alert"
      style={{
        background: 'var(--danger-100)',
        color: 'var(--danger-600)',
        padding: '1.0rem 1.2rem',
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--fs-14)',
        fontWeight: 600,
      }}
    >
      {errors.detail}
    </div>
  ) : null

  // The frozen styles.css carries no disabled state for .btn, and a
  // full-strength primary button that does nothing when clicked reads as
  // broken. Dimmed inline rather than editing the design contract.
  const submitDisabled = busy || !agreed
  const submitStyle = submitDisabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined

  const termsCheckbox = (
    <label className="check-row" style={{ alignItems: 'flex-start' }}>
      <input
        type="checkbox"
        style={{ marginTop: '0.3rem' }}
        checked={agreed}
        onChange={(e) => setAgreed(e.target.checked)}
      />
      <span className="text-sm">
        I agree to the terms of use and consent to my information being shared with
        authorised responders for recovery coordination.
      </span>
    </label>
  )

  return (
    <div className="auth-scene">
      <main className="auth-shell auth-shell--wide">
        <span className="auth-brand">
          <span className="logo__mark">
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0"
              />
            </svg>
          </span>
          <span className="name">HighGround</span>
        </span>

        <h1 className="auth-title">Create an account</h1>
        <p className="auth-sub">
          Register once, then submit and track every recovery request for your household.
        </p>

        <div className="auth-card">
          <div className="grid-2" style={{ gap: '1.6rem', marginBottom: '3.2rem' }}>
            <button
              type="button"
              className={`radio-card${accountType === 'resident' ? ' radio-card--selected' : ''}`}
              onClick={() => setAccountType('resident')}
              style={{ textAlign: 'left', cursor: 'pointer' }}
            >
              <HouseIcon />
              <div>
                <div className="title">Resident</div>
                <div className="desc">I need recovery assistance for my household</div>
              </div>
            </button>

            <button
              type="button"
              className={`radio-card${accountType === 'organisation' ? ' radio-card--selected' : ''}`}
              onClick={() => setAccountType('organisation')}
              style={{ textAlign: 'left', cursor: 'pointer' }}
            >
              <BuildingIcon />
              <div>
                <div className="title">Organisation</div>
                <div className="desc">NGO, volunteer team, or disaster office</div>
              </div>
            </button>
          </div>

          {applying ? (
            <form className="stack" style={{ gap: '2.4rem' }} onSubmit={handleSubmit}>
              {errorBanner}

              <div className="input-group">
                <div className="field">
                  <label htmlFor="requested_role">
                    Role you are applying for <span className="required">*</span>
                  </label>
                  <select
                    id="requested_role"
                    className="input"
                    value={requestedRole}
                    onChange={(e) => setRequestedRole(e.target.value)}
                    required
                  >
                    <option value="">Select your role</option>
                    {APPLICABLE_ROLES.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </select>
                  {fieldError('requested_role')}
                </div>
                <div className="field">
                  <label htmlFor="organization">
                    Organisation <span className="required">*</span>
                  </label>
                  <select
                    id="organization"
                    className="input"
                    value={organizationId}
                    onChange={(e) => setOrganizationId(e.target.value)}
                    required
                  >
                    <option value="">Select your organisation</option>
                    {organizations.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name} — {org.type_display}
                      </option>
                    ))}
                  </select>
                  {fieldError('organization')}
                </div>
              </div>

              <div className="field">
                <label htmlFor="documents">
                  Supporting documents <span className="required">*</span>
                </label>
                <input
                  id="documents"
                  className="input"
                  type="file"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={(e) => setDocuments(Array.from(e.target.files))}
                />
                {fieldError('documents') || (
                  <span className="help">
                    Organisation registration, staff ID, or an authorisation letter.
                    PDF, JPEG or PNG, up to 5 MB each.
                  </span>
                )}
                {documents.length > 0 && (
                  <span className="help" style={{ color: 'var(--grey-900)', fontWeight: 600 }}>
                    {documents.length} file{documents.length === 1 ? '' : 's'} attached:{' '}
                    {documents.map((file) => file.name).join(', ')}
                  </span>
                )}
              </div>

              <IdentityFields
                form={form}
                update={update}
                fieldError={fieldError}
                errors={errors}
              />

              {termsCheckbox}

              <div className="auth-note" style={{ margin: 0, color: 'var(--grey-700)' }}>
                <span>
                  <span style={{ color: 'var(--grey-900)', fontWeight: 700, display: 'block' }}>
                    Your account starts as a resident account.
                  </span>
                  A district administrator reviews your documents before the role is granted.
                  You can sign in and track the application in the meantime.
                </span>
              </div>

              <button
                className="btn btn--primary btn--full"
                type="submit"
                disabled={submitDisabled}
                style={submitStyle}
              >
                {busy ? 'Submitting application…' : 'Submit application'}
              </button>
            </form>
          ) : (
            <form className="stack" style={{ gap: '2.4rem' }} onSubmit={handleSubmit}>
              {errorBanner}

              <IdentityFields
                form={form}
                update={update}
                fieldError={fieldError}
                errors={errors}
              />

              {termsCheckbox}

              <button
                className="btn btn--primary btn--full"
                type="submit"
                disabled={submitDisabled}
                style={submitStyle}
              >
                {busy ? 'Creating account…' : 'Create account'}
              </button>
            </form>
          )}
        </div>

        <p className="auth-alt">
          Already registered?{' '}
          <button
            onClick={onShowLogin}
            style={{
              background: 'none',
              border: 0,
              padding: 0,
              cursor: 'pointer',
              color: 'var(--teal-300)',
              fontWeight: 600,
              font: 'inherit',
            }}
          >
            Log in
          </button>
        </p>
      </main>
    </div>
  )
}
