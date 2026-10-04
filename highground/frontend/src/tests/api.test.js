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
