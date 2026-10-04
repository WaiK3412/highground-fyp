// Describe household next steps using auditable task states/counts rather than invented recovery percentages.
export const STATUS_UI = {
  submitted: {
    badge: 'badge--new',
    next: 'Waiting for a district officer to review it',
  },
  needs_info: {
    badge: 'badge--escalated',
    next: 'The district office has asked for more information',
  },
  verified: {
    badge: 'badge--verified',
    next: 'Verified — waiting for a response team to take it on',
  },
  claimed: {
    badge: 'badge--assigned',
    next: 'A response team has taken this on',
  },
  in_progress: {
    badge: 'badge--progress',
    next: 'Work is under way',
  },
  pending_confirm: {
    badge: 'badge--progress',
    next: 'Waiting for you to confirm the work is finished',
  },
  closed: {
    badge: 'badge--resolved',
    next: 'Closed',
  },
  rejected: {
    badge: 'badge--escalated',
    next: 'Not accepted — open the case for the reason given',
  },
}

export const CLOSED_STATUSES = new Set(['closed', 'rejected'])
