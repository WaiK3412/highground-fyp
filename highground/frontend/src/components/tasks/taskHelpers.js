// Match the server's upload limits; photos remain optional at every stage.
export const MAX_PHOTOS = 5

export const MAX_PHOTO_BYTES = 5 * 1024 * 1024

// Same tones as the case queue, so a priority class reads the same on both screens.
export function priorityChipClass(priorityClass) {
  if (priorityClass === 1) return 'score score--high score--sm'
  if (priorityClass === 2) return 'score score--medium score--sm'
  return 'score score--low score--sm'
}

export function errorText(err) {
  const fields = err.fields || {}
  for (const key of ['photos', 'stage', 'caption', 'note', 'safety_acknowledged', 'status', 'lead_user_id', 'safety_note', 'detail']) {
    if (fields[key]) return Array.isArray(fields[key]) ? fields[key].join(' ') : String(fields[key])
  }
  return err.message
}
