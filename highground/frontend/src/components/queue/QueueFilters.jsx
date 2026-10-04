const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'verified', label: 'Verified' },
  { value: 'claimed', label: 'Claimed' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'pending_confirm', label: 'Awaiting confirmation', officerOnly: true },
]

const HELP_FILTERS = [
  { value: '', label: 'All' },
  { value: 'cleanup', label: 'Cleanup' },
  { value: 'repair', label: 'Repair' },
  { value: 'essential_items', label: 'Essential items' },
  { value: 'agriculture', label: 'Agriculture' },
  { value: 'other', label: 'Other' },
]

// classes-1.0 (scoring/classes.py): the class number is the filter value.
const PRIORITY_FILTERS = [
  { value: '', label: 'All' },
  { value: '1', label: '1 Health-critical' },
  { value: '2', label: '2 At risk' },
  { value: '3', label: '3 Standard' },
]

export default function QueueFilters({ user, status, priority, help, search, invalidateQueue, setStatus, setPriority, setHelp, setSearch }) {
  return (
    <>
        <div className="case-queue__filters">
          <div className="case-queue__filter-group" role="group" aria-label="Case status">
            <span className="case-queue__filter-label" aria-hidden="true">Status</span>
            {STATUS_FILTERS.filter((filter) => !filter.officerOnly || user.role === 'disaster_officer').map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`filter-chip${status === filter.value ? ' filter-chip--active' : ''}`}
                aria-pressed={status === filter.value}
                onClick={() => {
                  if (status === filter.value) return
                  invalidateQueue()
                  setStatus(filter.value)
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="case-queue__filter-group" role="group" aria-label="Priority class">
            <span className="case-queue__filter-label" aria-hidden="true">Priority</span>
            {PRIORITY_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`filter-chip${priority === filter.value ? ' filter-chip--active' : ''}`}
                aria-pressed={priority === filter.value}
                onClick={() => {
                  if (priority === filter.value) return
                  invalidateQueue()
                  setPriority(filter.value)
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="case-queue__filter-group" role="group" aria-label="Type of help">
            <span className="case-queue__filter-label" aria-hidden="true">Help</span>
            {HELP_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`filter-chip${help === filter.value ? ' filter-chip--active' : ''}`}
                aria-pressed={help === filter.value}
                onClick={() => {
                  if (help === filter.value) return
                  invalidateQueue()
                  setHelp(filter.value)
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            className="input"
            style={{ maxWidth: '24rem' }}
            aria-label="Search cases by reference or village"
            placeholder="Search reference, village…"
            value={search}
            onChange={(e) => {
              invalidateQueue()
              setSearch(e.target.value)
            }}
          />
        </div>
        {priority && <p className="case-queue__filter-note">Cases awaiting verification appear under Priority: All.</p>}
    </>
  )
}
