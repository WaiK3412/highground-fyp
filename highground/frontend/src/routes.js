/**
 * Which web address shows which screen, and who may open it.
 *
 * Screens are still switched in React state; this module only translates
 * between that state and the address bar, so the browser's Back, Forward and
 * reload work. The server still enforces every permission: these rules only
 * decide where to send someone who opens an address they cannot use.
 */

// Order matters only for readability; each pattern is matched in full.
const ROUTES = [
  { screen: 'landing', pattern: '/' },
  { screen: 'login', pattern: '/login' },
  { screen: 'register', pattern: '/register' },
  { screen: 'forgot', pattern: '/forgot-password' },
  { screen: 'reset', pattern: '/reset-password/:uid/:token' },
  { screen: 'confirm', pattern: '/confirm-email/:token' },
  { screen: 'recovery', pattern: '/my-cases' },
  { screen: 'recovery', pattern: '/my-cases/:id' },
  { screen: 'submit', pattern: '/request' },
  { screen: 'notifications', pattern: '/notifications' },
  { screen: 'appeals', pattern: '/appeals' },
  { screen: 'profile', pattern: '/profile' },
  { screen: 'queue', pattern: '/queue' },
  { screen: 'queue', pattern: '/queue/:id' },
  { screen: 'tasks', pattern: '/tasks' },
  { screen: 'duplicates', pattern: '/duplicates' },
  { screen: 'duplicates', pattern: '/duplicates/:id' },
  { screen: 'rules', pattern: '/rules' },
]

// Email links work whatever state the browser is in.
const FROM_EMAIL = ['reset', 'confirm']

const ALLOWED = {
  signedOut: ['landing', 'login', 'register', 'forgot', ...FROM_EMAIL],
  community_member: ['recovery', 'submit', 'notifications', 'appeals', 'profile', ...FROM_EMAIL],
  disaster_officer: ['queue', 'notifications', 'rules', 'appeals', 'duplicates', ...FROM_EMAIL],
  ngo_volunteer: ['queue', 'tasks', 'notifications', 'rules', 'appeals', ...FROM_EMAIL],
  // Administrators work in the Django admin; the app only shows them a link to it.
  system_admin: ['landing', ...FROM_EMAIL],
}

const HOME = {
  signedOut: '/',
  community_member: '/my-cases',
  disaster_officer: '/queue',
  ngo_volunteer: '/queue',
  system_admin: '/',
}

const NO_PARAMS = { id: null, uid: null, token: null }

/** Turn an address into { screen, id, uid, token }; screen is null if nothing matches. */
export function parsePath(pathname) {
  const parts = segments(pathname)
  for (const route of ROUTES) {
    const params = match(segments(route.pattern), parts)
    if (params) return { screen: route.screen, ...NO_PARAMS, ...params }
  }
  return { screen: null, ...NO_PARAMS }
}

/** The address for a screen, e.g. pathFor('recovery', { id: 42 }) → '/my-cases/42'. */
export function pathFor(screen, params = {}) {
  const given = Object.keys(params).filter((key) => params[key] != null)
  const route = ROUTES.find(
    (candidate) => candidate.screen === screen && sameNames(paramNames(candidate.pattern), given),
  )
  if (!route) throw new Error(`No address for screen "${screen}" with ${given.join(', ') || 'no parameters'}`)
  return route.pattern.replace(/:(\w+)/g, (_, name) => encodeURIComponent(params[name]))
}

export function homePath(role) {
  return HOME[role || 'signedOut'] || '/'
}

export function isAllowed(role, screen) {
  return (ALLOWED[role || 'signedOut'] || []).includes(screen)
}

function segments(path) {
  return path.split('/').filter(Boolean)
}

function paramNames(pattern) {
  return segments(pattern).filter((part) => part.startsWith(':')).map((part) => part.slice(1))
}

function sameNames(a, b) {
  return a.length === b.length && a.every((name) => b.includes(name))
}

// Compare segment by segment; ":id" must be a whole number, other parameters any text.
function match(patternParts, parts) {
  if (patternParts.length !== parts.length) return null
  const params = {}
  for (const [index, part] of patternParts.entries()) {
    const value = decodeURIComponent(parts[index])
    if (part === ':id') {
      if (!/^\d+$/.test(value)) return null
      params.id = Number(value)
    } else if (part.startsWith(':')) {
      params[part.slice(1)] = value
    } else if (part !== value) {
      return null
    }
  }
  return params
}
