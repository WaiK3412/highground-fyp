import { Fragment } from 'react'
import { Icon, PATHS } from '../../icons'
import { DAMAGE_CATEGORIES, FLOOD_DEPTHS, LIVEABILITY, ACCESS_LEVELS, URGENCY, VULNERABILITY_FLAGS, NEEDS_FLAGS } from './options'

function villageLabel(rows, code) {
  const village = rows.find((row) => row.code === code)
  return village ? `${village.name}, ${village.district}` : ''
}

function labelFor(list, value) {
  return list.find((o) => o.value === value)?.label ?? '—'
}

export default function StepReview({ user, data, goTo, villages }) {
  const flagLabels = (list, values) =>
    values.length ? values.map((v) => labelFor(list, v)).join(' · ') : 'None'

  const section = (title, step, rows) => (
    <div className="card mb-24">
      <div className="row--between" style={{ marginBottom: '1.6rem' }}>
        <h2 className="h3">{title}</h2>
        <button className="btn btn--ghost btn--sm" onClick={() => goTo(step)}>
          Edit
        </button>
      </div>
      <dl className="kv">
        {rows.map(([term, value]) => (
          <Fragment key={term}>
            <dt>{term}</dt>
            <dd>{value || '—'}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  )

  return (
    <>
      {section('Household', 0, [
        ['Full name', user.full_name],
        ['Household members', `${data.household_size}`],
        ['Mobile number', user.phone],
        ['Village / area', villageLabel(villages.rows, data.location_code)],
        ['Address or landmark', data.address],
        [
          'Map pin',
          data.pin
            ? `Placed (${data.pin.latitude.toFixed(5)}, ${data.pin.longitude.toFixed(5)})`
            : 'Not placed — your village will be used',
        ],
      ])}

      {section('Home & damage', 1, [
        ['Type of help', labelFor(DAMAGE_CATEGORIES, data.damage_category)],
        ['Also need help with', flagLabels(DAMAGE_CATEGORIES, data.also_need.filter((value) => value !== data.damage_category))],
        ['Description', data.description],
        ['Floodwater depth', labelFor(FLOOD_DEPTHS, data.flood_depth)],
        ['Liveable', labelFor(LIVEABILITY, data.liveability)],
        ['Vehicle access', labelFor(ACCESS_LEVELS, data.access_level)],
      ])}

      {section('Safety & needs', 2, [
        ['Health or safety', labelFor(URGENCY, data.urgency)],
        ['Vulnerability', flagLabels(VULNERABILITY_FLAGS, data.vulnerability_flags)],
        ['Essentials needed', flagLabels(NEEDS_FLAGS, data.needs_flags)],
      ])}

      {section('Photos', 3, [['Selected', data.photos.length ? `${data.photos.length} photo(s)` : 'None']])}

      <div className="banner banner--info mb-24">
        <Icon path={PATHS.info} />
        <span className="body text-sm">
          <span className="title">What happens next.</span> An officer checks your request before it is
          prioritised and passed to relief organisations.
        </span>
      </div>
    </>
  )
}
