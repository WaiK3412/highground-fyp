// Supply appeals (ADR-021, ADR-025): how an appeal's items, deadline and
// drop-off point are shown. Kept apart from the screens so they can be tested.

/** One entry per item: split on commas, semicolons and new lines, except inside brackets. */
export function splitItems(text = '') {
  const items = []
  let depth = 0
  let current = ''
  for (const char of text) {
    if (char === '(') depth += 1
    if (char === ')') depth = Math.max(0, depth - 1)
    if (depth === 0 && (char === ',' || char === ';' || char === '\n')) {
      items.push(current)
      current = ''
    } else {
      current += char
    }
  }
  items.push(current)
  return items.map((item) => item.trim()).filter(Boolean)
}

/** Whole calendar days from today to the needed-until date ("2026-11-08"); negative once passed. */
export function daysLeft(neededUntil, now = new Date()) {
  const [year, month, day] = neededUntil.split('-').map(Number)
  const deadline = Date.UTC(year, month - 1, day)
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((deadline - today) / 86_400_000)
}

export function deadlineLabel(neededUntil, now = new Date()) {
  const days = daysLeft(neededUntil, now)
  if (days < 0) return 'Date passed'
  if (days === 0) return 'Needed today'
  return days === 1 ? '1 day left' : `${days} days left`
}

/** Directions in Google Maps to a drop-off point, searched by its public name and address. */
export function directionsUrl(point) {
  const destination = [point.name, point.address, point.area].filter(Boolean).join(', ')
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`
}
