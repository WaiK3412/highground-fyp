import { Icon, PATHS } from '../../icons'
import Required from './Required'
import { URGENCY, VULNERABILITY_FLAGS, NEEDS_FLAGS } from './options'

export default function StepNeeds({ data, set }) {
  const toggle = (key, value) => {
    const current = data[key]
    set({ [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value] })
  }

  return (
    <>
      <div className="banner banner--danger mb-24">
        <Icon path={PATHS.warning} />
        <span className="body text-sm">
          <span className="title">In danger right now? Call 999.</span>
          <br />
          HighGround coordinates recovery help — it is not an emergency rescue service. If anyone is
          in life-threatening danger, call 999 or the Civil Defence Force (APM) immediately.
        </span>
      </div>

      <div className="card mb-24">
        <h2 className="h3 mb-4">Safety and urgent needs</h2>
        <p className="text-sm text-muted mb-24">
          This is what decides how quickly your case is looked at.
        </p>

        <div className="stack gap-24">
          <div className="field">
            <label>
              Is anyone&rsquo;s health or safety affected? <Required />
            </label>
            <div className="stack gap-12">
              {URGENCY.map((option) => (
                <label
                  key={option.value}
                  className={`radio-card${data.urgency === option.value ? ' radio-card--selected' : ''}`}
                  style={{ alignItems: 'center', cursor: 'pointer' }}
                >
                  <input
                    type="radio"
                    name="urgency"
                    checked={data.urgency === option.value}
                    onChange={() => set({ urgency: option.value })}
                    style={{ width: '1.8rem', height: '1.8rem', accentColor: 'var(--teal-700)' }}
                  />
                  <div>
                    <div className="title">{option.label}</div>
                    <div className="desc">{option.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label>
              Household vulnerability{' '}
              <span className="text-muted font-normal">
                (tick all that apply — this helps us prioritise)
              </span>
            </label>
            <div className="stack gap-8">
              {VULNERABILITY_FLAGS.map((option) => (
                <label key={option.value} className="check-row cursor-pointer">
                  <input
                    type="checkbox"
                    checked={data.vulnerability_flags.includes(option.value)}
                    onChange={() => toggle('vulnerability_flags', option.value)}
                  />{' '}
                  {option.label}
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label>
              Has your household run out of any essentials?{' '}
              <span className="text-muted font-normal">
                (tick anything you can&rsquo;t get right now)
              </span>
            </label>
            <div className="stack gap-8">
              {NEEDS_FLAGS.map((option) => (
                <label key={option.value} className="check-row cursor-pointer">
                  <input
                    type="checkbox"
                    checked={data.needs_flags.includes(option.value)}
                    onChange={() => toggle('needs_flags', option.value)}
                  />{' '}
                  {option.label}
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
