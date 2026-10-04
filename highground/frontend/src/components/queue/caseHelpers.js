// An NGO may claim an open job once the household request is verified.
const CLAIMABLE_CASE = new Set(['verified', 'claimed', 'in_progress', 'pending_confirm'])

export function openJobsFor(user, item) {
  if (user.role !== 'ngo_volunteer' || !CLAIMABLE_CASE.has(item.status)) return []
  return (item.jobs || []).filter((job) => job.status === 'open')
}

export function confirmationDays(since) {
  return Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 86400000))
}
