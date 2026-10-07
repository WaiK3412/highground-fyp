// "child_under_5" reads badly to the people it describes.
const humanise = (flag) => flag.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
const list = (flags) => (flags?.length ? flags.map(humanise).join(' · ') : '—')

/** The household's own answers, shown to whoever may see the full case. Extra rows go in children. */
export default function CaseFacts({ detail, children }) {
  return (
    <dl className="kv">
      {detail.household_contact && (
        <>
          <dt>Household contact</dt>
          <dd>
            {detail.household_contact.name}, <a href={`tel:${detail.household_contact.phone}`}>{detail.household_contact.phone}</a>
          </dd>
        </>
      )}
      <dt>Type</dt>
      <dd>{detail.damage_category_display}</dd>
      <dt>Flood depth</dt>
      <dd>{detail.flood_depth_display}</dd>
      <dt>Home liveable</dt>
      <dd>{detail.liveability_display}</dd>
      <dt>Urgency</dt>
      <dd>{detail.urgency_display}</dd>
      <dt>Access</dt>
      <dd>{detail.access_level_display}</dd>
      <dt>Household</dt>
      <dd>
        {detail.household_size} {detail.household_size === 1 ? 'member' : 'members'}
        {detail.vulnerability_flags?.length > 0 && ` · ${list(detail.vulnerability_flags)}`}
      </dd>
      <dt>Essential needs</dt>
      <dd>{list(detail.needs_flags)}</dd>
      {children}
    </dl>
  )
}
