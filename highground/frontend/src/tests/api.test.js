import assert from 'node:assert/strict'
import { File } from 'node:buffer'
import { afterEach, beforeEach, test } from 'node:test'
import { api } from '../api.js'

let originalFetch
let originalDocument

beforeEach(() => {
  originalFetch = globalThis.fetch
  originalDocument = globalThis.document
  globalThis.document = { cookie: 'csrftoken=synthetic-csrf' }
})

afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalDocument === undefined) delete globalThis.document
  else globalThis.document = originalDocument
})

test('task photos use multipart, the photos field, session credentials and CSRF', async () => {
  const result = { photos: [{ url: '/api/case-photos/7/file/', stage: 'after' }] }
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/api/tasks/42/photos/')
    assert.equal(options.method, 'POST')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.headers['X-CSRFToken'], 'synthetic-csrf')
    assert.equal(options.headers['Content-Type'], undefined)
    assert.equal(options.body.get('stage'), 'after')
    assert.equal(options.body.get('caption'), 'Mud removed')
    assert.deepEqual(options.body.getAll('photos').map((file) => file.name), ['work.jpg'])
    assert.equal(options.body.get('documents'), null)
    return new Response(JSON.stringify(result), { status: 201 })
  }
  assert.deepEqual(await api.addTaskPhotos(42, 'after', [new File(['pixels'], 'work.jpg', { type: 'image/jpeg' })], 'Mud removed'), result)
})

test('officer close submits a distinct outcome and contact note as JSON', async () => {
  const reason = { outcome: 'household_unreachable', note: 'Called today; no answer.' }
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/api/cases/9/close/')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['X-CSRFToken'], 'synthetic-csrf')
    assert.deepEqual(JSON.parse(options.body), reason)
    return new Response(JSON.stringify({ status: 'closed' }), { status: 200 })
  }
  assert.deepEqual(await api.closeOnBehalf(9, reason), { status: 'closed' })
})

test('photo validation failures remain errors with their field messages', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ photos: ['Choose a readable image.'] }), { status: 400 })
  await assert.rejects(
    () => api.addTaskPhotos(42, 'after', []),
    (error) => error.status === 400 && error.fields.photos[0] === 'Choose a readable image.',
  )
})

// Stub fetch for one POST and check what the client sent: path, CSRF and body.
function expectPost(path, body, reply = { ok: true }) {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, path)
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['X-CSRFToken'], 'synthetic-csrf')
    if (body !== undefined) assert.deepEqual(JSON.parse(options.body), body)
    return new Response(JSON.stringify(reply), { status: 200 })
  }
}

test('donate posts items to the appeal donations endpoint with CSRF', async () => {
  expectPost('/api/appeals/7/donations/', { items: 'Rice' })
  assert.deepEqual(await api.donate(7, 'Rice'), { ok: true })
})

test('cancelDonation and receiveDonation post to their own endpoints', async () => {
  expectPost('/api/donations/3/cancel/')
  await api.cancelDonation(3)
  expectPost('/api/donations/3/receive/')
  await api.receiveDonation(3)
})

test('requestPasswordReset posts the email', async () => {
  expectPost('/api/auth/password-reset/', { email: 'siti@example.my' })
  await api.requestPasswordReset('siti@example.my')
})

test('confirmPasswordReset posts uid, token and both passwords', async () => {
  expectPost('/api/auth/password-reset/confirm/', {
    uid: 'MQ', token: 'abc-123', new_password1: 'NewPass2026', new_password2: 'NewPass2026',
  })
  await api.confirmPasswordReset('MQ', 'abc-123', 'NewPass2026', 'NewPass2026')
})

test('confirmEmail posts the token and resendConfirmation the email', async () => {
  expectPost('/api/auth/confirm-email/', { token: 'signed:token' })
  await api.confirmEmail('signed:token')
  expectPost('/api/auth/confirm-email/resend/', { email: 'new@example.my' })
  await api.resendConfirmation('new@example.my')
})

test('twoFactorSetup and twoFactorVerify post with CSRF', async () => {
  expectPost('/api/auth/two-factor/setup/')
  await api.twoFactorSetup()
  expectPost('/api/auth/two-factor/verify/', { code: '123456' })
  await api.twoFactorVerify('123456')
})

test('publicAppeals reads the open appeals without signing in', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/public/appeals/')
    assert.equal(options.method, 'GET')
    return new Response(JSON.stringify({ results: [] }), { status: 200 })
  }
  assert.deepEqual(await api.publicAppeals(), { results: [] })
})

test('two-step settings: enable, confirm with a code, disable with a code', async () => {
  expectPost('/api/auth/two-factor/enable/')
  await api.enableTwoFactor()
  expectPost('/api/auth/two-factor/enable/confirm/', { code: '123456' })
  await api.confirmTwoFactor('123456')
  expectPost('/api/auth/two-factor/disable/', { code: '654321' })
  await api.disableTwoFactor('654321')
})
