import assert from 'node:assert/strict'
import { test } from 'node:test'
import { homePath, isAllowed, parsePath, pathFor } from '../routes.js'

const EMPTY = { id: null, uid: null, token: null }

test('round trip for every screen', () => {
  const cases = [
    ['landing'], ['login'], ['register'], ['forgot'],
    ['reset', { uid: 'MQ', token: 'abc-123' }], ['confirm', { token: 'tok' }],
    ['recovery'], ['recovery', { id: 42 }], ['submit'], ['notifications'], ['appeals'], ['profile'],
    ['queue'], ['queue', { id: 7 }], ['tasks'], ['duplicates'], ['duplicates', { id: 3 }], ['rules'],
  ]
  for (const [screen, params = {}] of cases) {
    assert.deepEqual(parsePath(pathFor(screen, params)), { screen, ...EMPTY, ...params }, screen)
  }
})

test('the addresses people see', () => {
  assert.equal(pathFor('landing'), '/')
  assert.equal(pathFor('recovery'), '/my-cases')
  assert.equal(pathFor('recovery', { id: 42 }), '/my-cases/42')
  assert.equal(pathFor('forgot'), '/forgot-password')
  assert.equal(pathFor('submit'), '/request')
})

test('case ids parse as numbers', () => {
  assert.deepEqual(parsePath('/my-cases/42'), { screen: 'recovery', ...EMPTY, id: 42 })
  assert.equal(parsePath('/my-cases/abc').screen, null)
})

test('reset and confirm keep their tokens', () => {
  assert.deepEqual(parsePath('/reset-password/MQ/abc-123'), { screen: 'reset', id: null, uid: 'MQ', token: 'abc-123' })
  assert.equal(parsePath('/confirm-email/eyJ1Ijo1fQ:1tX:abc').token, 'eyJ1Ijo1fQ:1tX:abc')
})

test('unknown, proxied and trailing-slash paths', () => {
  assert.equal(parsePath('/api/x').screen, null)
  assert.equal(parsePath('/nope').screen, null)
  assert.equal(parsePath('/queue/').screen, 'queue')
})

test('role permissions', () => {
  assert.equal(isAllowed('community_member', 'queue'), false)
  assert.equal(isAllowed('disaster_officer', 'tasks'), false)
  assert.equal(isAllowed('ngo_volunteer', 'duplicates'), false)
  assert.equal(isAllowed(null, 'appeals'), false)
  assert.equal(isAllowed(null, 'reset'), true)
  assert.equal(isAllowed('ngo_volunteer', 'reset'), true)
  assert.equal(isAllowed('community_member', 'login'), false)
})

test('home paths', () => {
  assert.equal(homePath(null), '/')
  assert.equal(homePath('community_member'), '/my-cases')
  assert.equal(homePath('disaster_officer'), '/queue')
  assert.equal(homePath('ngo_volunteer'), '/queue')
  assert.equal(homePath('system_admin'), '/')
})
