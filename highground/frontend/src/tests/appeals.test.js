import assert from 'node:assert/strict'
import { test } from 'node:test'
import { daysLeft, deadlineLabel, directionsUrl, splitItems } from '../appeals.js'

test('items split on commas, semicolons and new lines, but not inside brackets', () => {
  assert.deepEqual(
    splitItems('Mops, buckets; bleach\nRubber boots (sizes 8, 9 and 10),  ,\n'),
    ['Mops', 'buckets', 'bleach', 'Rubber boots (sizes 8, 9 and 10)'],
  )
  assert.deepEqual(splitItems(''), [])
})

test('days left counts calendar days, whatever the time of day', () => {
  const lateEvening = new Date(2026, 10, 1, 23, 50)
  const earlyMorning = new Date(2026, 10, 1, 0, 5)
  for (const now of [lateEvening, earlyMorning]) {
    assert.equal(daysLeft('2026-11-01', now), 0)
    assert.equal(daysLeft('2026-11-02', now), 1)
    assert.equal(daysLeft('2026-11-08', now), 7)
    assert.equal(daysLeft('2026-10-31', now), -1)
  }
})

test('deadline labels', () => {
  const now = new Date(2026, 10, 1, 12, 0)
  assert.equal(deadlineLabel('2026-10-30', now), 'Date passed')
  assert.equal(deadlineLabel('2026-11-01', now), 'Needed today')
  assert.equal(deadlineLabel('2026-11-02', now), '1 day left')
  assert.equal(deadlineLabel('2026-11-05', now), '4 days left')
})

test('directions search for the drop-off point by name, address and area', () => {
  const url = new URL(directionsUrl({ name: 'Balai Raya Pasir Mas', address: 'Jalan Che Latiff', area: 'Pasir Mas' }))
  assert.equal(url.origin + url.pathname, 'https://www.google.com/maps/dir/')
  assert.equal(url.searchParams.get('api'), '1')
  assert.equal(url.searchParams.get('destination'), 'Balai Raya Pasir Mas, Jalan Che Latiff, Pasir Mas')
})
