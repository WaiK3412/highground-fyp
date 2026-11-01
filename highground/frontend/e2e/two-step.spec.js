/**
 * A resident switches on two-step sign-in in their profile and is shown backup
 * codes; the next sign-in asks for a code, and a backup code works instead.
 */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, hexFromSetupKey, resetRateLimits, signedIn, totp } from './helpers.js'

test('setup keys decode to the secret they were made from', () => {
  // RFC 4648 example: "foobar" is MZXW6YTBOI in base32.
  expect(hexFromSetupKey('MZXW6YTBOI')).toBe(Buffer.from('foobar').toString('hex'))
})

test('a resident turns on two-step sign-in, then needs a code to sign in', async ({ browser }) => {
  resetRateLimits()  // the earlier specs' staff sign-ins share this IP's two-step budget
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/profile')
  await resident.getByRole('button', { name: 'Turn on' }).click()
  const setupKey = await resident.locator('p', { hasText: 'Cannot scan?' }).locator('strong').innerText()
  const secret = hexFromSetupKey(setupKey)
  await resident.locator('#two-factor-code').fill(totp(secret))
  await resident.getByRole('button', { name: 'Turn on two-step sign-in' }).click()
  await expect(resident.getByText('Two-step sign-in is on.')).toBeVisible()
  const codes = resident.getByRole('list', { name: 'Backup codes' }).getByRole('listitem')
  await expect(codes).toHaveCount(10)
  const backupCode = await codes.first().innerText()
  await resident.getByRole('button', { name: 'I have saved my codes' }).click()
  await expect(resident.getByText('Backup codes left: 10')).toBeVisible()

  const fresh = await browser.newContext()
  const page = await fresh.newPage()
  await page.goto('/login')
  await page.locator('#email').fill(ACCOUNTS.resident.email)
  await page.locator('#password').fill(ACCOUNTS.resident.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByRole('heading', { name: 'Enter your code' })).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)

  // Without the phone: a backup code signs in once.
  await page.getByRole('button', { name: 'Lost your phone? Use a backup code' }).click()
  await page.locator('#backup-code').fill(backupCode)
  await page.getByRole('button', { name: 'Sign in with backup code' }).click()
  await expect(page).toHaveURL(/\/my-cases$/)
})
