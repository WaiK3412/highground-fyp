/**
 * API client. Session auth (ADR-001), so the cookie rides along on its own;
 * Django then wants that cookie's CSRF token echoed back in a header.
 */

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

async function request(path, { method = 'GET', body, files, fileField = 'documents' } = {}) {
  // A file cannot be put inside JSON, so an upload switches the whole request
  // to multipart/form-data. The browser sets Content-Type itself in that case
  // — it has to, because it must append the boundary marker.
  const headers = files ? {} : { 'Content-Type': 'application/json' }

  if (method !== 'GET') {
    // Read per request: Django issues a fresh token on login.
    const token = getCookie('csrftoken')
    if (token) headers['X-CSRFToken'] = token
  }

  let payload
  if (files) {
    payload = new FormData()
    Object.entries(body || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return
      // FormData stringifies everything, so an array would arrive as
      // "elderly,disability" and stop being a list. Send it as JSON and let
      // the serializer parse it back.
      payload.append(key, Array.isArray(value) ? JSON.stringify(value) : value)
    })
    // Same field name repeated once per file — that is how request.FILES
    // .getlist("documents") sees them all on the Django side.
    files.forEach((file) => payload.append(fileField, file))
  } else if (body) {
    payload = JSON.stringify(body)
  }

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: payload,
  })

  if (response.status === 204) return null

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(data?.detail || 'Something went wrong. Please try again.')
    error.status = response.status
    error.code = data?.code
    error.data = data
    // DRF sends {field: [messages]}; keep them so each shows under its field.
    if (data && typeof data === 'object' && !data.detail) error.fields = data
    throw error
  }
  return data
}

export const api = {
  // Gets the CSRF cookie in place before the first POST.
  primeCsrf: () => request('/api/auth/csrf/'),
  register: (payload, files) =>
    request('/api/auth/register/', { method: 'POST', body: payload, files }),
  organizations: () => request('/api/organizations/'),
  login: (email, password) =>
    request('/api/auth/login/', { method: 'POST', body: { email, password } }),
  // Staff: the code step after the password (ADR-026).
  twoFactorSetup: () => request('/api/auth/two-factor/setup/', { method: 'POST' }),
  twoFactorVerify: (code) =>
    request('/api/auth/two-factor/verify/', { method: 'POST', body: { code } }),
  // A resident's own choice to use two-step sign-in (staff always have it).
  twoFactorStatus: () => request('/api/auth/two-factor/'),
  enableTwoFactor: () => request('/api/auth/two-factor/enable/', { method: 'POST' }),
  confirmTwoFactor: (code) =>
    request('/api/auth/two-factor/enable/confirm/', { method: 'POST', body: { code } }),
  disableTwoFactor: (code) =>
    request('/api/auth/two-factor/disable/', { method: 'POST', body: { code } }),
  logout: () => request('/api/auth/logout/', { method: 'POST' }),
  me: () => request('/api/auth/me/'),
  confirmEmail: (token) =>
    request('/api/auth/confirm-email/', { method: 'POST', body: { token } }),
  resendConfirmation: (email) =>
    request('/api/auth/confirm-email/resend/', { method: 'POST', body: { email } }),
  requestPasswordReset: (email) =>
    request('/api/auth/password-reset/', { method: 'POST', body: { email } }),
  confirmPasswordReset: (uid, token, password1, password2) =>
    request('/api/auth/password-reset/confirm/', {
      method: 'POST',
      body: { uid, token, new_password1: password1, new_password2: password2 },
    }),
  cases: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v),
    ).toString()
    return request('/api/cases/' + (query ? `?${query}` : ''))
  },
  caseMap: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v),
    ).toString()
    return request('/api/cases/map/' + (query ? `?${query}` : ''))
  },
  duplicates: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined),
    ).toString()
    return request('/api/duplicates/' + (query ? `?${query}` : ''))
  },
  duplicate: (id) => request(`/api/duplicates/${id}/`),
  decideDuplicate: (id, decision, note = '') =>
    request(`/api/duplicates/${id}/decide/`, { method: 'POST', body: { decision, note } }),
  createCase: (payload, files) =>
    request('/api/cases/', { method: 'POST', body: payload, files, fileField: 'photos' }),
  caseDetail: (id) => request(`/api/cases/${id}/`),
  locations: () => request('/api/locations/'),
  // Help jobs (ADR-020): each type of help is claimed and finished on its own.
  claimJob: (id) => request(`/api/jobs/${id}/claim/`, { method: 'POST' }),
  releaseJob: (id, reason) =>
    request(`/api/jobs/${id}/release/`, { method: 'POST', body: { reason } }),
  verifyCase: (id, decision, note) =>
    request(`/api/cases/${id}/verify/`, { method: 'POST', body: { decision, note } }),
  taskBoard: () => request('/api/tasks/'),
  caseTasks: (id) => request(`/api/cases/${id}/tasks/`),
  createTask: (caseId, payload) =>
    request(`/api/cases/${caseId}/tasks/`, { method: 'POST', body: payload }),
  updateTask: (id, payload) =>
    request(`/api/tasks/${id}/`, { method: 'PATCH', body: payload }),
  addTaskPhotos: (taskId, stage, files, caption = '') =>
    request(`/api/tasks/${taskId}/photos/`, {
      method: 'POST', body: { stage, caption }, files, fileField: 'photos',
    }),
  closeOnBehalf: (caseId, reason) =>
    request(`/api/cases/${caseId}/close/`, { method: 'POST', body: reason }),
  completeJob: (id) => request(`/api/jobs/${id}/complete/`, { method: 'POST' }),
  confirmJob: (id, decision, note = '') =>
    request(`/api/jobs/${id}/confirm/`, { method: 'POST', body: { decision, note } }),
  unmetHelp: () => request('/api/jobs/unmet/'),
  stats: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v),
    ).toString()
    return request('/api/cases/stats/' + (query ? `?${query}` : ''))
  },
  // Screen 18 — how priority works (classes-1.0), read-only.
  priorityRules: () => request('/api/priority-rules/'),
  // Notifications are event-log rows addressed to this user (ADR-004).
  notifications: () => request('/api/notifications/'),
  markNotificationRead: (id) => request(`/api/notifications/${id}/read/`, { method: 'POST' }),
  markAllNotificationsRead: () => request('/api/notifications/read-all/', { method: 'POST' }),
  appeals: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/api/appeals/${query ? `?${query}` : ''}`)
  },
  createAppeal: (payload) => request('/api/appeals/', { method: 'POST', body: payload }),
  updateAppeal: (id, payload) =>
    request(`/api/appeals/${id}/`, { method: 'PATCH', body: payload }),
  dropOffPoints: () => request('/api/drop-off-points/'),
  // The landing page's list, readable without signing in (ADR-025).
  publicAppeals: () => request('/api/public/appeals/'),
  // Donations (ADR-025): residents record them, the appeal's NGO confirms receipt.
  donate: (appealId, items) =>
    request(`/api/appeals/${appealId}/donations/`, { method: 'POST', body: { items } }),
  appealDonations: (appealId) => request(`/api/appeals/${appealId}/donations/`),
  myDonations: () => request('/api/donations/'),
  cancelDonation: (id) => request(`/api/donations/${id}/cancel/`, { method: 'POST' }),
  receiveDonation: (id) => request(`/api/donations/${id}/receive/`, { method: 'POST' }),
  replyToCase: (id, payload) =>
    request(`/api/cases/${id}/reply/`, { method: 'POST', body: payload }),
  overridePriority: (id, priorityClass, reason) =>
    request(`/api/cases/${id}/priority-override/`, {
      method: 'POST', body: { priority_class: priorityClass, reason },
    }),
  updateProfile: (payload) => request('/api/auth/me/', { method: 'PATCH', body: payload }),
}
