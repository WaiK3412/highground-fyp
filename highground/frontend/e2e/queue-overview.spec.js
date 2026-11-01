/**
 * The queue's overview counts (FR13, FR16): each count opens the list it counts,
 * and a second click returns to the whole queue.
 */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, resetRateLimits, signedIn } from './helpers.js'

// Both tests sign staff in; the earlier specs' sign-ins share this IP's two-step budget.
test.beforeEach(() => resetRateLimits())

test('an officer opens the requests to verify from the overview, then the whole queue again', async ({ browser }) => {
  const officer = await signedIn(browser, ACCOUNTS.officer)
  const count = officer.getByRole('button', { name: /to verify/ })
  const toVerify = Number((await count.locator('.queue-stat__value').textContent()).trim())
  expect(toVerify).toBeGreaterThan(0)

  await count.click()
  await expect(count).toHaveAttribute('aria-pressed', 'true')
  await expect(officer.locator('#queue-status')).toHaveValue('submitted')
  const cards = officer.locator('.ops-card')
  await expect(cards).toHaveCount(toVerify)
  // Every request listed is one still waiting for the officer's decision.
  await expect(cards.getByRole('button', { name: 'Review & decide' })).toHaveCount(toVerify)

  await count.click()
  await expect(officer.locator('#queue-status')).toHaveValue('')
  await expect(officer.getByRole('button', { name: 'Clear filters' })).toHaveCount(0)
})

test("an NGO responder lists only its own organisation's work from the overview", async ({ browser }) => {
  const ngo = await signedIn(browser, ACCOUNTS.ngo)
  const count = ngo.getByRole('button', { name: /held by your organisation/ })
  const ours = Number((await count.locator('.queue-stat__value').textContent()).trim())
  expect(ours).toBeGreaterThan(0)

  await count.click()
  const cards = ngo.locator('.ops-card')
  await expect(cards).toHaveCount(ours)
  // Each card names this organisation as holding a type of help.
  for (const card of await cards.all()) {
    await expect(card.getByText(/your organisation/)).not.toHaveCount(0)
  }
})
