/**
 * The main journey across three roles: a resident's request is verified by the
 * district officer, a relief organisation claims and finishes the work, and
 * the household confirms it, which closes the case.
 */

import { expect, test } from '@playwright/test'
import { ACCOUNTS, api, fixture, signedIn } from './helpers.js'

test('a request goes from submission to the household confirming the work', async ({ browser }) => {
  // Resident: the five request steps.
  const resident = await signedIn(browser, ACCOUNTS.resident)
  await resident.goto('/request')
  await resident.locator('#request-village').selectOption(fixture().villageCode)
  await resident.locator('#request-address').fill('Lot 12, Jalan Ujian')
  await resident.getByRole('button', { name: 'Continue' }).click()

  await resident.locator('label', { hasText: 'Mud, debris and silt removal' }).click()
  await resident.locator('#request-description').fill('Mud through the ground floor after the flood.')
  await resident.locator('label', { hasText: 'Knee height' }).click()
  await resident.locator('#request-liveability').selectOption('partial')
  await resident.locator('#request-access').selectOption('normal')
  await resident.getByRole('button', { name: 'Continue' }).click()

  await resident.locator('label', { hasText: 'No safety concerns' }).click()
  await resident.getByRole('button', { name: 'Continue' }).click()
  await resident.getByRole('button', { name: 'Continue' }).click()  // photos are optional
  await resident.getByRole('button', { name: 'Submit request' }).click()
  await expect(resident).toHaveURL(/\/my-cases$/)

  const cases = (await api(resident, 'GET', '/api/cases/')).results
  const submitted = cases.reduce((newest, item) => (item.id > newest.id ? item : newest))
  const reference = `#${submitted.reference}`
  expect(submitted.status).toBe('submitted')

  // Officer: verify it from the queue.
  const officer = await signedIn(browser, ACCOUNTS.officer)
  await officer.locator('.ops-card', { hasText: reference }).getByRole('button', { name: 'Review & decide' }).click()
  await expect(officer).toHaveURL(new RegExp(`/queue/${submitted.id}$`))
  await officer.getByRole('button', { name: 'Verify', exact: true }).click()
  await expect.poll(async () => (await api(officer, 'GET', `/api/cases/${submitted.id}/`)).status).toBe('verified')

  // NGO: claim the cleanup job from the queue.
  const ngo = await signedIn(browser, ACCOUNTS.ngo)
  await ngo.locator('.ops-card', { hasText: reference }).getByRole('button', { name: 'Claim cleanup' }).click()
  await expect.poll(async () => {
    const detail = await api(ngo, 'GET', `/api/cases/${submitted.id}/`)
    return detail.jobs.find((job) => job.help_type === 'cleanup')?.status
  }).toBe('claimed')

  // The field work itself (one task, started then done) goes through the
  // API with the NGO's own session; the board's own buttons are covered elsewhere.
  const me = await api(ngo, 'GET', '/api/auth/me/')
  const job = (await api(ngo, 'GET', `/api/cases/${submitted.id}/`)).jobs.find((j) => j.help_type === 'cleanup')
  const task = await api(ngo, 'POST', `/api/cases/${submitted.id}/tasks/`, {
    job_id: job.id, title: 'Clear the ground floor', task_type: 'cleanup', lead_user_id: me.id,
  })
  await api(ngo, 'PATCH', `/api/tasks/${task.id}/`, { status: 'in_progress' })
  await api(ngo, 'PATCH', `/api/tasks/${task.id}/`, { status: 'done' })

  await ngo.goto('/tasks')
  await ngo.locator('.case-strip', { hasText: reference }).getByRole('button', { name: 'Request resident confirmation' }).click()
  await expect(ngo.getByText('The resident has been asked to confirm completion.')).toBeVisible()

  // Resident: confirm the work, which closes the case.
  await resident.goto(`/my-cases/${submitted.id}`)
  await resident.getByRole('button', { name: 'Confirm complete' }).click()
  await expect.poll(async () => (await api(resident, 'GET', `/api/cases/${submitted.id}/`)).status).toBe('closed')
})
