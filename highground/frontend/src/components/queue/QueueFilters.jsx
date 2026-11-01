// One compact row: three lists and a search, so the queue or map keeps the screen.
const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'submitted', label: 'Submitted', officerOnly: true },
  { value: 'verified', label: 'Verified' },
  { value: 'claimed', label: 'Claimed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'pending_confirm', label: 'Awaiting the household' },
]

// classes-1.0 (priority/classes.py): the class number is the filter value.
const PRIORITY_FILTERS = [
  { value: '', label: 'All' },
  { value: '1', label: '1 Health-critical' },
  { value: '2', label: '2 At risk' },
  { value: '3', label: '3 Standard' },
]

const HELP_FILTERS = [
  { value: '', label: 'All' },
  { value: 'cleanup', label: 'Cleanup' },
  { value: 'repair', label: 'Repair' },
  { value: 'essential_items', label: 'Essential items' },
  { value: 'agriculture', label: 'Agriculture' },
  { value: 'other', label: 'Other' },
]

const SCOPES = { open_help: 'Help not yet taken', mine: 'Held by your organisation' }

function Select({ id, label, value, options, onChange }) {
  return (
    <label className="queue-select" htmlFor={id}>
      <span>{label}</span>
      <select id={id} className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  )
}

export default function QueueFilters({ user, current, apply, setSearch, shown, total }) {
  const { status, priority, help, scope, search } = current
  const change = (name) => (value) => apply({ status, priority, help, scope, [name]: value })
  const filtered = Boolean(status || priority || help || scope || search)
  const statuses = STATUS_FILTERS.filter((option) => !option.officerOnly || user.role === 'disaster_officer')

  return (
    <>
      <div className="case-queue__filters">
        <Select id="queue-status" label="Status" value={status} options={statuses} onChange={change('status')} />
        <Select id="queue-priority" label="Priority" value={priority} options={PRIORITY_FILTERS} onChange={change('priority')} />
        <Select id="queue-help" label="Help" value={help} options={HELP_FILTERS} onChange={change('help')} />
        <input
          className="input case-queue__search"
          aria-label="Search cases by reference or village"
          placeholder="Search reference, village…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {filtered && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => { setSearch(''); apply({}) }}>
            Clear filters
          </button>
        )}
        {total != null && (
          <span className="case-queue__shown" role="status">
            {scope && <strong>{SCOPES[scope]} · </strong>}
            {filtered ? `${shown ?? '…'} of ${total} cases` : `${total} ${total === 1 ? 'case' : 'cases'}`}
          </span>
        )}
      </div>
      {priority && <p className="case-queue__filter-note">Cases awaiting verification appear under Priority: All.</p>}
    </>
  )
}
