/**
 * Add HighGround to an authenticator app, then enter its code: at a staff
 * member's first sign-in, or when a resident turns it on in their profile.
 */

import { api } from '../../api'
import { useLoad } from '../../useLoad'
import AuthAlert from './AuthAlert'
import TwoFactorCode from './TwoFactorCode'

export default function TwoFactorSetup({
  onVerified, onTimedOut, loadSetup = api.twoFactorSetup, verify, buttonLabel = 'Finish setup and sign in',
}) {
  const { data: setup, loading, error } = useLoad(loadSetup, [])

  if (loading) return <p role="status" className="text-sm">Preparing your QR code…</p>
  if (error) return <AuthAlert>{error}</AuthAlert>

  return (
    <div className="stack" style={{ gap: '1.6rem' }}>
      <ol className="text-sm" style={{ margin: 0, paddingLeft: '2rem' }}>
        <li>Open an authenticator app on your phone (for example Google or Microsoft Authenticator).</li>
        <li>Add an account and scan this QR code.</li>
        <li>Enter the 6-digit code the app shows.</li>
      </ol>
      <img
        src={setup.qr_data_uri}
        alt="QR code for your authenticator app"
        style={{ width: '18rem', height: '18rem', alignSelf: 'center', background: '#fff' }}
      />
      <p className="text-xs text-muted" style={{ margin: 0, wordBreak: 'break-all' }}>
        Cannot scan? Type this key into the app instead: <strong>{setup.setup_key}</strong>
      </p>
      <TwoFactorCode onVerified={onVerified} onTimedOut={onTimedOut} verify={verify} buttonLabel={buttonLabel} />
    </div>
  )
}
