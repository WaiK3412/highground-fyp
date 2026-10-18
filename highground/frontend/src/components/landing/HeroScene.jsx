/**
 * The landing hero picture: a kampung house on high ground above receding
 * water, with two cards in the app's own style. The case is the fictional
 * seed-data example (FRC-1042), not a real household.
 */

const LABEL_FONT = { fontFamily: 'Plus Jakarta Sans, sans-serif', fontSize: 12, fontStyle: 'italic' }

export default function HeroScene() {
  return (
    <div className="hero-scene">
      <svg viewBox="0 0 480 360" fill="none" role="img" aria-label="Kampung house standing on high ground above receding flood water">
        <path d="M0 330 Q 40 324, 80 330 T 160 330 T 240 330 T 320 330 T 400 330 T 480 330 L 480 360 L 0 360 Z" fill="#8AD5DB" opacity="0.55" />
        <path d="M0 336 Q 60 330, 120 336 T 240 336 T 360 336 T 480 336" stroke="#2D9AA3" strokeWidth="2.5" opacity="0.6" />
        <path d="M28 360 C 70 344, 110 308, 240 306 C 370 308 410 344, 452 360 Z" fill="#E9DCC3" stroke="#BC6C4F" strokeWidth="1.5" />
        <path d="M120 326 C 170 312, 310 312, 360 326" stroke="#BC6C4F" strokeWidth="1.5" opacity="0.5" />
        <path d="M82 342 C 160 322, 320 322, 398 342" stroke="#BC6C4F" strokeWidth="1.5" opacity="0.32" />
        <rect x="150" y="232" width="10" height="74" rx="2" fill="#155E63" />
        <rect x="320" y="232" width="10" height="74" rx="2" fill="#155E63" />
        <rect x="200" y="236" width="8" height="70" rx="2" fill="#155E63" opacity="0.7" />
        <rect x="272" y="236" width="8" height="70" rx="2" fill="#155E63" opacity="0.7" />
        <rect x="136" y="150" width="208" height="86" rx="6" fill="#FFFFFF" stroke="#D6D0C8" strokeWidth="2.5" />
        <rect x="226" y="178" width="30" height="58" rx="3" fill="#D9F1F2" stroke="#1B7179" strokeWidth="2" />
        <rect x="160" y="178" width="34" height="28" rx="3" fill="#F3FAFA" stroke="#D6D0C8" strokeWidth="2" />
        <rect x="286" y="178" width="34" height="28" rx="3" fill="#F3FAFA" stroke="#D6D0C8" strokeWidth="2" />
        <path d="M120 152 L240 84 L360 152" stroke="#1B7179" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="#F3FAFA" />
        <path d="M148 136 L240 84 L332 136" stroke="#1B7179" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" opacity="0.4" />
        <line x1="96" y1="216" x2="384" y2="216" stroke="#155E63" strokeWidth="2" strokeDasharray="7 6" opacity="0.65" />
        <text x="388" y="220" fill="#155E63" opacity="0.8" style={LABEL_FONT}>flood peak</text>
        <text x="14" y="322" fill="#155E63" opacity="0.8" style={LABEL_FONT}>today</text>
        <circle cx="412" cy="64" r="22" fill="#D9F1F2" stroke="#2D9AA3" strokeWidth="2.5" />
      </svg>

      <div className="card hero-chip" style={{ top: '2rem', left: '-1.6rem', width: '25rem' }}>
        <div className="text-strong text-sm">#FRC-1042 · verified</div>
        <div className="text-xs text-muted">Priority class 1 — Health-critical</div>
      </div>
      <div className="card hero-chip" style={{ bottom: '1.2rem', right: '-1.2rem', width: '26rem' }}>
        <div className="text-strong text-sm">Cleanup job claimed</div>
        <div className="text-xs text-muted">Mercy Relief Malaysia · responder assigned</div>
      </div>
    </div>
  )
}
