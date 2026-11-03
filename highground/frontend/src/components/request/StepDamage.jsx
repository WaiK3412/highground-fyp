import Required from './Required'
import { DAMAGE_CATEGORIES, FLOOD_DEPTHS, LIVEABILITY, ACCESS_LEVELS } from './options'

/* Use the frozen house SVG with an answer-driven waterline; withhold water until a depth is chosen. */
function DepthHouse({ waterY }) {
  const crest = waterY - 4
  const wave =
    `M10 ${waterY} Q 22 ${crest} 34 ${waterY} T 58 ${waterY} T 82 ${waterY} T 106 ${waterY} ` +
    `T 130 ${waterY} T 154 ${waterY} T 178 ${waterY} T 202 ${waterY} T 226 ${waterY} ` +
    `L 230 ${waterY} L 230 150 L 10 150 Z`

  return (
    <div className="depth-picker__house">
      <svg viewBox="0 0 240 170" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="depth-water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#8AD5DB" stopOpacity="0.85" />
            <stop offset="1" stopColor="#2D9AA3" stopOpacity="0.9" />
          </linearGradient>
        </defs>
        <polygon points="38,60 120,16 202,60" fill="#F2EEE7" stroke="#A8A099" strokeWidth="2" strokeLinejoin="round" />
        <rect x="50" y="60" width="140" height="90" fill="#FFFFFF" stroke="#A8A099" strokeWidth="2" />
        <rect x="80" y="105" width="26" height="45" fill="#F2EEE7" stroke="#A8A099" strokeWidth="2" />
        <rect x="130" y="85" width="32" height="26" fill="#F3FAFA" stroke="#A8A099" strokeWidth="2" />
        <circle cx="218" cy="102" r="6" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="108" x2="218" y2="134" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="116" x2="210" y2="126" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="116" x2="226" y2="126" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="134" x2="212" y2="150" stroke="#746D66" strokeWidth="2" />
        <line x1="218" y1="134" x2="224" y2="150" stroke="#746D66" strokeWidth="2" />
        <line x1="10" y1="150" x2="230" y2="150" stroke="#746D66" strokeWidth="2" />
        {waterY != null && (
          <>
            <path d={wave} fill="url(#depth-water)" />
            <line x1="10" y1={waterY} x2="230" y2={waterY} stroke="#155E63" strokeWidth="1.5" strokeDasharray="5 4" />
          </>
        )}
      </svg>
    </div>
  )
}

export default function StepDamage({ data, set }) {
  const toggle = (key, value) => {
    const current = data[key]
    set({ [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] })
  }

  return (
    <>
      <div className="card mb-24">
        <h2 className="h3 mb-4">What kind of help do you need?</h2>
        <p className="text-sm text-muted mb-24">
          Pick the closest match. An officer will confirm the details.
        </p>

        <div className="stack gap-12">
          {DAMAGE_CATEGORIES.map((option) => (
            <label
              key={option.value}
              className={`radio-card${data.damage_category === option.value ? ' radio-card--selected' : ''}`}
              style={{ alignItems: 'center', cursor: 'pointer' }}
            >
              <input
                type="radio"
                name="damage_category"
                checked={data.damage_category === option.value}
                onChange={() => set({ damage_category: option.value })}
                style={{ width: '1.8rem', height: '1.8rem', accentColor: 'var(--teal-700)' }}
              />
              <span>
                <span className="title">{option.label}</span>
                <span className="desc"> — {option.desc}</span>
              </span>
            </label>
          ))}
        </div>

        {/* ADR-020: separate jobs let different organisations take different types of help. */}
        {data.damage_category && (
          <div className="field" style={{ marginTop: '2.4rem' }}>
            <label>
              Do you also need help with anything else?{' '}
              <span className="text-muted font-normal">(optional)</span>
            </label>
            <div className="stack gap-8">
              {DAMAGE_CATEGORIES.filter((option) => option.value !== data.damage_category).map((option) => (
                <label key={option.value} className="check-row cursor-pointer">
                  <input
                    type="checkbox"
                    checked={data.also_need.includes(option.value)}
                    onChange={() => toggle('also_need', option.value)}
                  />{' '}
                  {option.label}
                </label>
              ))}
            </div>
            <p className="help">Different organisations may help with each one.</p>
          </div>
        )}
      </div>

      <div className="card mb-24">
        <div className="stack gap-24">
          <div className="field">
            <label htmlFor="request-description">
              Describe the damage and what you need <Required />
            </label>
            <textarea
              id="request-description"
              className="input"
              rows={5}
              value={data.description}
              onChange={(e) => set({ description: e.target.value })}
              placeholder="e.g. Floodwater reached 1 metre inside the house. Thick mud in every room, damaged furniture needs removal. We have two elderly family members and cannot do the heavy cleanup ourselves."
            />
          </div>

          <div className="field">
            <label>
              How high did the floodwater reach inside your home? <Required />
            </label>
            <div className="depth-picker">
              <DepthHouse waterY={FLOOD_DEPTHS.find((o) => o.value === data.flood_depth)?.waterY ?? null} />
              <div className="depth-picker__options">
              {FLOOD_DEPTHS.map((option) => (
                <label
                  key={option.value}
                  className={`depth-option${data.flood_depth === option.value ? ' depth-option--selected' : ''} cursor-pointer`}
                >
                  <input
                    type="radio"
                    name="flood_depth"
                    checked={data.flood_depth === option.value}
                    onChange={() => set({ flood_depth: option.value })}
                  />
                  <span>
                    <span className="title">{option.label}</span> <span className="desc">— {option.desc}</span>
                  </span>
                </label>
              ))}
              </div>
            </div>
          </div>

          <div className="input-group">
            <div className="field">
              <label htmlFor="request-liveability">
                Is your home currently liveable? <Required />
              </label>
              <select
                id="request-liveability"
                className="input"
                value={data.liveability}
                onChange={(e) => set({ liveability: e.target.value })}
              >
                {LIVEABILITY.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="request-access">
                Can vehicles currently reach your home? <Required />
              </label>
              <select
                id="request-access"
                className="input"
                value={data.access_level}
                onChange={(e) => set({ access_level: e.target.value })}
              >
                {ACCESS_LEVELS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
