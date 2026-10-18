/** Opened from the sign-up email (/confirm-email/<token>): confirm, then log in. */

import { api } from '../api'
import { useDocumentTitle } from '../useDocumentTitle'
import { useLoad } from '../useLoad'
import AuthAlert from '../components/auth/AuthAlert'
import AuthLayout from '../components/auth/AuthLayout'
import ResendConfirmation from '../components/auth/ResendConfirmation'

export default function ConfirmEmail({ token, onShowLogin }) {
  useDocumentTitle('Confirm your email')
  // Confirming twice is harmless, so a repeated request (or a reload) is fine.
  const { data, loading, error } = useLoad(
    () => api.primeCsrf().then(() => api.confirmEmail(token)),
    [token],
  )

  return (
    <AuthLayout title="Confirm your email">
      <div className="auth-card stack" style={{ gap: '1.6rem' }}>
        {loading && <p role="status" className="text-sm">Confirming…</p>}
        {data && (
          <>
            <AuthAlert tone="success">{data.detail}</AuthAlert>
            <button className="btn btn--primary btn--full" onClick={onShowLogin}>Log in</button>
          </>
        )}
        {error && (
          <>
            <AuthAlert>{error}</AuthAlert>
            <ResendConfirmation />
          </>
        )}
      </div>
    </AuthLayout>
  )
}
