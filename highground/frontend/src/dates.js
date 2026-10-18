/** "18 Oct 2026" from a date ("2026-10-18") or a timestamp. */
export function formatDay(value) {
  // A bare date is local midnight, not UTC: without the time it can show the day before.
  const date = value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value)
  return date.toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })
}
