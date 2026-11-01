/**
 * Profile panel: a resident may switch two-step sign-in on or off for their own
 * account (ADR-026). Staff always have it, so for them it only says so. Anyone
 * with it on can get new backup codes (ADR-028).
 */

import { useState } from 'react'
import { api } from '../../api'
import { useLoad } from '../../useLoad'
import BackupCodes from './BackupCodes'
import TwoFactorCode from './TwoFactorCode'
import TwoFactorSetup from './TwoFactorSetup'

export default function TwoFactorSettings() {
  const { data: status, setData: setStatus, loading, error } = useLoad(() => api.twoFactorStatus(), [])
  // null, 'enabling', 'disabling' or 'new-codes': which code form is open.
  const [changing, setChanging] = useState(null)
  const [message, setMessage] = useState(null)
  // Codes just made, shown once until the person says they have saved them.
  const [shownCodes, setShownCodes] = useState(null)

  function changed({ backup_codes, ...next }, text) {
    setStatus(next)
    setChanging(null)
    setMessage(text)
    setShownCodes(backup_codes || null)
  }

  function open(form) {
    setMessage(null)
    setChanging(form)
  }

  return (
    <section className="panel stack" style={{ maxWidth: '48rem', marginTop: 'var(--sp-24)', gap: '1.2rem' }}>
      <h2 className="panel-title">Two-step sign-in</h2>
      <p className="text-sm text-muted" style={{ margin: 0 }}>
        Optional for households: after your password, enter a 6-digit code from an
        authenticator app on your phone, so a stolen password alone cannot open your account.
      </p>
      {loading && <p role="status" className="text-sm">Loading…</p>}
      {error && <p role="alert" className="text-sm">Could not load this setting: {error}</p>}
      {message && <p role="status" className="text-sm">{message}</p>}

      {shownCodes && (
        <BackupCodes codes={shownCodes} onDone={() => setShownCodes(null)} />
      )}

      {status && !changing && !shownCodes && (
        <>
          <div className="row--between" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
            <span className="text-sm">
              <strong>{status.enabled ? 'On' : 'Off'}</strong>
              {status.required && ' — required for staff accounts'}
            </span>
            {!status.required && (
              <button
                className={`btn btn--sm ${status.enabled ? 'btn--ghost' : 'btn--primary'}`}
                onClick={() => open(status.enabled ? 'disabling' : 'enabling')}
              >
                {status.enabled ? 'Turn off' : 'Turn on'}
              </button>
            )}
          </div>
          {status.enabled && (
            <div className="row--between" style={{ gap: 'var(--sp-12)', flexWrap: 'wrap' }}>
              <span className="text-sm">
                Backup codes left: <strong>{status.backup_codes_left}</strong>
                {status.backup_codes_left <= 2 && ' — get new ones before you run out'}
              </span>
              <button className="btn btn--sm btn--ghost" onClick={() => open('new-codes')}>
                Get new backup codes
              </button>
            </div>
          )}
        </>
      )}

      {changing === 'enabling' && (
        <TwoFactorSetup
          loadSetup={api.enableTwoFactor}
          verify={api.confirmTwoFactor}
          buttonLabel="Turn on two-step sign-in"
          onVerified={(next) => changed(next, 'Two-step sign-in is on. You will need a code at your next sign-in.')}
        />
      )}
      {changing === 'disabling' && (
        <TwoFactorCode
          verify={api.disableTwoFactor}
          buttonLabel="Turn off two-step sign-in"
          onVerified={(next) => changed(next, 'Two-step sign-in is off.')}
        />
      )}
      {changing === 'new-codes' && (
        <TwoFactorCode
          verify={api.newBackupCodes}
          buttonLabel="Make new backup codes"
          onVerified={(next) => changed(next, 'New backup codes made. Your old codes no longer work.')}
        />
      )}
      {changing && (
        <button className="btn btn--ghost btn--sm" style={{ alignSelf: 'flex-start' }} onClick={() => setChanging(null)}>
          Cancel
        </button>
      )}
    </section>
  )
}
