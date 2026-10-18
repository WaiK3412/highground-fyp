/** The message box on signed-out screens: red for errors, green for good news. */

const TONES = {
  error: { background: 'var(--danger-100)', color: 'var(--danger-600)', role: 'alert' },
  success: { background: 'var(--success-100)', color: 'var(--success-600)', role: 'status' },
}

export default function AuthAlert({ tone = 'error', children }) {
  const { role, ...colours } = TONES[tone]
  return (
    <div
      role={role}
      style={{
        ...colours,
        padding: '1.0rem 1.2rem',
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--fs-14)',
        fontWeight: 600,
      }}
    >
      {children}
    </div>
  )
}
