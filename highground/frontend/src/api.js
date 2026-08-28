/**
 * API client. Session auth (ADR-001), so the cookie rides along on its own;
 * Django then wants that cookie's CSRF token echoed back in a header.
 */

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

async function request(path, { method = 'GET', body, files } = {}) {
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
      if (value !== undefined && value !== null && value !== '') payload.append(key, value)
    })
    // Same field name repeated once per file — that is how request.FILES
    // .getlist("documents") sees them all on the Django side.
    files.forEach((file) => payload.append('documents', file))
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
  logout: () => request('/api/auth/logout/', { method: 'POST' }),
  me: () => request('/api/auth/me/'),
  cases: (params = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v),
    ).toString()
    return request('/api/cases/' + (query ? `?${query}` : ''))
  },
  createCase: (payload) => request('/api/cases/', { method: 'POST', body: payload }),
  caseDetail: (id) => request(`/api/cases/${id}/`),
  claimCase: (id) => request(`/api/cases/${id}/claim/`, { method: 'POST' }),
  verifyCase: (id, decision, note) =>
    request(`/api/cases/${id}/verify/`, { method: 'POST', body: { decision, note } }),
  stats: () => request('/api/cases/stats/'),
}
