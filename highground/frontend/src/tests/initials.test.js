import assert from 'node:assert/strict'
import { test } from 'node:test'
import { initials } from '../initials.js'

test('initials skip patronymic particles and honorifics', () => {
  const cases = [
    ['Siti binti Rahman', 'SR'],
    ['Encik Zulkifli bin Hassan', 'ZH'],
    ['Ramasamy a/l Muniandy', 'RM'],
    ['Aisyah Tan', 'AT'],
    ['aisyah', 'A'],
    ['', '?'],
  ]
  for (const [name, expected] of cases) assert.equal(initials(name), expected, name)
})
