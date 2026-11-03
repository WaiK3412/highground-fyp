import { Icon, PATHS } from '../../icons'
import { pinProblem } from '../../geo'
import PinPicker from '../../pages/PinPicker'
import Required from './Required'

// The form lists villages under their district, as the location table does.
function byDistrict(rows) {
  const groups = new Map()
  rows.forEach((row) => {
    if (!groups.has(row.district)) groups.set(row.district, [])
    groups.get(row.district).push(row)
  })
  return [...groups.entries()]
}

export default function StepHousehold({ user, data, set, villages, onRetryVillages, onNavigate }) {
  const village = villages.rows.find((row) => row.code === data.location_code)

  // Clear mismatched village pins to prevent a pair the server would reject.
  function chooseVillage(code) {
    const next = villages.rows.find((row) => row.code === code)
    const keepPin = data.pin && next && !pinProblem(next, data.pin.latitude, data.pin.longitude)
    set({ location_code: code, pin: keepPin ? data.pin : null })
  }

  return (
    <>
      <div className="card mb-24">
        <h2 className="h3 mb-4">Who needs help?</h2>
        <p className="text-sm text-muted mb-24">
          These come from your account. To change them, go to{' '}
          {onNavigate ? (
            <button type="button" className="link-button text-sm" onClick={() => onNavigate('profile')}>
              My profile
            </button>
          ) : 'My profile'}.
        </p>

        <div className="stack gap-24">
          <dl className="kv">
            <dt>Full name</dt>
            <dd>{user.full_name || '—'}</dd>
            <dt>Mobile number</dt>
            <dd>{user.phone || '—'}</dd>
          </dl>
          <div className="input-group">
            <div className="field">
              <label htmlFor="request-household-size">
                Household members <Required />
              </label>
              <select
                id="request-household-size"
                className="input"
                value={data.household_size}
                onChange={(e) => set({ household_size: Number(e.target.value) })}
              >
                {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n} {n === 1 ? 'person' : 'people'}
                  </option>
                ))}
              </select>
              <span className="help">Everyone currently living in the home.</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-24">
        <h2 className="h3 mb-4">Where is your home?</h2>
        <p className="text-sm text-muted mb-24">
          Pick your village, then drop a pin on your house — kampung addresses can be hard to find, and
          an accurate pin helps teams reach you faster.
        </p>

        <div className="stack gap-24">
          <div className="input-group">
            <div className="field">
              <label htmlFor="request-village">
                Village / area <Required />
              </label>
              <select
                id="request-village"
                className="input"
                value={data.location_code}
                onChange={(e) => chooseVillage(e.target.value)}
                disabled={villages.loading || Boolean(villages.error)}
              >
                <option value="">{villages.loading ? 'Loading villages…' : 'Choose your village…'}</option>
                {byDistrict(villages.rows).map(([district, rows]) => (
                  <optgroup key={district} label={district}>
                    {rows.map((v) => (
                      <option key={v.code} value={v.code}>
                        {v.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {villages.error || (!villages.loading && villages.rows.length === 0) ? (
                <p className="help text-danger" role="alert">
                  {villages.error ? 'Could not load villages.' : 'No villages are available yet.'}{' '}
                  <button
                    type="button"
                    onClick={onRetryVillages}
                    style={{ background: 'none', border: 0, padding: 0, color: 'inherit', textDecoration: 'underline', cursor: 'pointer', font: 'inherit' }}
                  >
                    Try again
                  </button>
                </p>
              ) : (
                <p className="help">
                  Choosing a village centres the map below. Not listed? Choose the nearest village and
                  describe the place.
                </p>
              )}
            </div>
            <div className="field">
              <label htmlFor="request-address">
                Address or landmark <Required />
              </label>
              <input
                id="request-address"
                className="input"
                type="text"
                value={data.address}
                onChange={(e) => set({ address: e.target.value })}
                placeholder="No. 14, Jalan Masjid, near the surau"
              />
              <span className="help">Road, house number, or a nearby landmark (masjid, balai raya, school).</span>
            </div>
          </div>

          {village ? (
            <PinPicker village={village} value={data.pin} onChange={(pin) => set({ pin })} />
          ) : (
            <p className="help">Choose your village to place a pin on your home.</p>
          )}

          {/* Must match accounts.permissions.may_see_exact_location. */}
          <div className="banner banner--info">
            <Icon path={PATHS.lock} />
            <span className="body text-sm">
              <span className="title">Your location stays private.</span> Your exact pin is visible only to
              the district office and the organisation that takes on your case — never publicly. Other
              organisations see only your village, not your pin or address.
            </span>
          </div>
        </div>
      </div>
    </>
  )
}
