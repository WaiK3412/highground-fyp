/**
 * FR1: someone who will act for an organisation applies on the registration
 * page's Organisation tab, can follow the application while it is under review,
 * and then reads the decision and its reason (FR20 decides it).
 *
 * The administrator's decision is made through the same model method the
 * administration console calls (reject_application), in the Django shell: the
 * demo seed gives administrators no authenticator, and the console's own
 * screens are covered by backend tests (test_verification, test_admin_records).
 */

import { expect, test } from '@playwright/test'
import { djangoShell } from './helpers.js'

const PASSWORD = 'Recovery-2026!'
const REASON = 'The authorisation letter is not signed by the organisation.'

test('an applicant sees the application under review, then the decision and its reason', async ({ page }) => {
  const email = `e2e-applicant-${Date.now()}@example.my`

  await page.goto('/register')
  await page.getByRole('button', { name: /Organisation/ }).click()
  await page.locator('#full_name').fill('Nurul Aina binti Yusof')
  await page.locator('#phone').fill('0123456789')
  await page.locator('#reg-email').fill(email)
  await page.locator('#reg-password').fill(PASSWORD)
  await page.locator('#password_confirm').fill(PASSWORD)
  await page.locator('#requested_role').selectOption('ngo_volunteer')
  const organisation = page.locator('#organization')
  await expect(organisation.locator('option').nth(1)).toBeAttached()
  await organisation.selectOption({ index: 1 })
  await page.locator('#documents').setInputFiles({
    name: 'authorisation-letter.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n%%EOF\n'),
  })
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Submit application' }).click()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()

  // The confirmation link goes by e-mail, which end-to-end runs print rather than send.
  djangoShell(`from accounts.models import UserAccount; UserAccount.objects.filter(email=${JSON.stringify(email)}).update(email_confirmed=True)`)

  await page.goto('/login')
  await page.locator('#email').fill(email)
  await page.locator('#password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByText('Your application to join as an NGO responder is under review.')).toBeVisible()

  djangoShell([
    'from accounts.models import UserAccount as U',
    'admin = U.objects.filter(role=U.Role.SYSTEM_ADMIN, is_active=True).order_by("id").first()',
    'assert admin, "no administrator account: create one with createsuperuser"',
    `U.objects.get(email=${JSON.stringify(email)}).reject_application(admin, ${JSON.stringify(REASON)})`,
  ].join('\n'))

  await page.reload()
  await expect(page.getByText('Your role application was not approved.')).toBeVisible()
  await expect(page.getByText(REASON)).toBeVisible()
})
