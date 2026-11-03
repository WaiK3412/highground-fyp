/** What each kind of visitor can reach, and the Back button inside the app. */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, signedIn, totp } from './helpers.js'

test('a visitor sees the landing page and open appeals, but no donor details', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /After the flood/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Log in to donate' }).first()).toBeVisible()
  // The seed has donations from these residents; the public page must not show them.
  await expect(page.getByText('Siti binti Rahman')).toHaveCount(0)
  await expect(page.getByText('2 mops and 3 buckets')).toHaveCount(0)
})

test('a signed-out visitor opening a signed-in address is asked to log in', async ({ page }) => {
  await page.goto('/appeals')
  await expect(page).toHaveURL(/\/login$/)
})

test('a resident opening the responder queue lands on their own cases', async ({ browser }) => {
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/queue')
  await expect(resident).toHaveURL(/\/my-cases$/)
})

test('Back closes an open case, then returns to the previous screen', async ({ browser }) => {
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/appeals')
  await resident.getByRole('link', { name: 'My Recovery' }).click()
  await resident.getByRole('button', { name: /#FRC-/ }).first().click()
  await expect(resident).toHaveURL(/\/my-cases\/\d+$/)
  await resident.goBack()
  await expect(resident).toHaveURL(/\/my-cases$/)
  await resident.goBack()
  await expect(resident).toHaveURL(/\/appeals$/)
})

test('the status banner opens the case it names, and My Recovery is the only case list', async ({ browser }) => {
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/my-cases')
  // The seeded household has a request waiting for its answer, so the banner names it.
  await expect(resident.getByText(/needs more information from you/)).toBeVisible()
  const openButton = resident.getByRole('button', { name: /^Open #FRC-\d+$/ })
  const reference = (await openButton.textContent()).replace('Open ', '')
  await openButton.click()
  await expect(resident).toHaveURL(/\/my-cases\/\d+$/)
  await expect(resident.locator('.text-strong.case-reference')).toHaveText(reference)
  await expect(resident.getByText('Your answer')).toBeVisible()
  await expect(openButton).toHaveCount(0)
  await expect(resident.getByRole('link', { name: /^My cases/ })).toHaveCount(0)
})

test('authenticator codes follow RFC 6238', () => {
  // The RFC's SHA-1 test vector: secret "12345678901234567890", time 59 s.
  const secret = Buffer.from('12345678901234567890').toString('hex')
  expect(totp(secret, 59_000, 8)).toBe('94287082')
})
