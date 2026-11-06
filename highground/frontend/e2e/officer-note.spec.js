/**
 * An officer's note goes to one household (FR8), so it must not follow the officer to the next
 * request. Manual test MT36 found a rejection carrying the note written for another request.
 */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, resetRateLimits, signedIn } from './helpers.js'

test.beforeEach(() => resetRateLimits())

test("an officer's unsent note does not follow them to another request", async ({ browser }) => {
  const officer = await signedIn(browser, ACCOUNTS.officer)
  await officer.getByRole('button', { name: /to verify/ }).click()
  const review = officer.locator('.ops-card').getByRole('button', { name: 'Review & decide' })

  await review.nth(0).click()
  const note = officer.getByLabel('Note to the household')
  await note.fill('A question for the first household.')

  await review.nth(1).click()
  await expect(note).toHaveValue('')
})
