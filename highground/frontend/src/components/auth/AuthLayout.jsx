/**
 * The frame shared by every signed-out screen (log in, register, password reset,
 * email confirmation): the teal scene, the brand, a title and a short subtitle.
 */

import Contours from '../Contours'

const BRAND_MARK = 'M2.5 12.5L4 11.5 12 5 20 11.5 21.5 12.5 M3 16q3-2 6 0t6 0t6 0 M3 19.5q3-2 6 0t6 0t6 0'

export default function AuthLayout({ title, subtitle, wide = false, decorated = true, children }) {
  return (
    <div className="auth-scene">
      {decorated && (
        <>
          <Contours className="auth-scene__contours auth-scene__contours--tl" scales={[[1, 0.05], [0.8, 0.07], [0.6, 0.09], [0.42, 0.11]]} />
          <Contours className="auth-scene__contours auth-scene__contours--br" scales={[[1, 0.05], [0.7, 0.08], [0.45, 0.11]]} />
          <svg className="auth-scene__ridge" viewBox="0 0 1440 110" preserveAspectRatio="none" aria-hidden="true">
            <path
              d="M0 74 C 240 44, 430 88, 720 64 C 990 44, 1210 90, 1440 60 L1440 110 L0 110 Z"
              fill="rgba(233, 220, 195, 0.10)"
            />
            <path
              d="M0 60 C 240 32, 430 74, 720 52 C 990 34, 1210 78, 1440 46"
              fill="none"
              stroke="rgba(233, 220, 195, 0.22)"
              strokeWidth="1.5"
            />
          </svg>
        </>
      )}

      <main className={`auth-shell${wide ? ' auth-shell--wide' : ''}`}>
        <span className="auth-brand">
          <span className="logo__mark">
            <svg fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d={BRAND_MARK} />
            </svg>
          </span>
          <span className="name">HighGround</span>
        </span>

        <h1 className="auth-title">{title}</h1>
        {subtitle && <p className="auth-sub">{subtitle}</p>}
        {children}
      </main>
    </div>
  )
}

/** A text-style button on the dark scene, e.g. "Create an account". */
export function AuthLinkButton({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: 'none',
        border: 0,
        // At least 24 px tall, the WCAG 2.2 minimum target size.
        padding: '0.2rem 0',
        minHeight: '2.4rem',
        cursor: 'pointer',
        color: 'var(--teal-300)',
        fontWeight: 600,
        font: 'inherit',
      }}
    >
      {children}
    </button>
  )
}
