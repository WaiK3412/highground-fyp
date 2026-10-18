/**
 * A resident records a donation to the demo appeal; the appeal's NGO is told,
 * marks it received, and the resident sees it received and is told too.
 */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, signedIn } from './helpers.js'

const APPEAL = 'Cleaning supplies for Pasir Mas households'
const ITEMS = 'Three buckets and a mop (end-to-end test)'

test('a donation is recorded, confirmed by the NGO, and both sides are notified', async ({ browser }) => {
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/appeals')
  const appealCard = resident.locator('li.card', { hasText: APPEAL })
  await appealCard.getByRole('button', { name: "I'll donate" }).click()
  await appealCard.getByLabel('What are you bringing?').fill(ITEMS)
  await appealCard.getByRole('button', { name: 'Record donation' }).click()
  const myDonation = resident.locator('section', { hasText: 'My donations' }).locator('li', { hasText: ITEMS })
  await expect(myDonation.getByText('Waiting for drop-off')).toBeVisible()

  const ngo = await signedIn(browser, ACCOUNTS.ngo)
  await ngo.goto('/notifications')
  await expect(ngo.getByText(`New donation coming for ${APPEAL}: ${ITEMS}`)).toBeVisible()

  await ngo.goto('/appeals')
  await ngo.getByRole('button', { name: /^Donations: \d+ waiting/ }).click()
  const row = ngo.locator('div.row--between', { hasText: ITEMS })
  await row.getByRole('button', { name: 'Mark received' }).click()
  await expect(ngo.getByText(/received by .+ on /).first()).toBeVisible()

  await resident.reload()
  await expect(myDonation.getByText('Received', { exact: true })).toBeVisible()
  await resident.goto('/notifications')
  await expect(resident.getByText(`Your donation to ${APPEAL} was received: ${ITEMS}`)).toBeVisible()
})
