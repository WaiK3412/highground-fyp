/** Shared pieces for the end-to-end tests: demo accounts, sign-in, authenticator codes. */

import { execFileSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect } from '@playwright/test'

const here = path.dirname(fileURLToPath(import.meta.url))
export const BACKEND = path.join(here, '..', '..', 'backend')
export const FIXTURE_FILE = path.join(here, '.fixture.json')

/** KEY=value lines from the backend .env, falling back to the process environment. */
export function backendEnv(name) {
  if (process.env[name]) return process.env[name]
  const file = path.join(BACKEND, '.env')
  if (!fs.existsSync(file)) return undefined
  const line = fs.readFileSync(file, 'utf8').split(/\r?\n/).find((l) => l.startsWith(`${name}=`))
  return line ? line.slice(name.length + 1).trim() : undefined
}

// Django keeps variables that are already set over .env, so an empty EMAIL_HOST
// makes test runs print emails instead of sending them through real SMTP.
export const CONSOLE_EMAIL_ENV = { ...process.env, EMAIL_HOST: '' }

// Seeded by manage.py seed_demo; all share its short demo password.
const DEMO_PASSWORD = 'demo'
export const ACCOUNTS = {
  resident: { email: backendEnv('DEMO_RESIDENT_EMAIL') || 'resident@hg.my', password: DEMO_PASSWORD },
  officer: { email: backendEnv('DEMO_OFFICER_EMAIL') || 'officer@hg.my', password: DEMO_PASSWORD, staff: true },
  ngo: { email: 'ngo@hg.my', password: DEMO_PASSWORD, staff: true },
}

export function fixture() {
  return JSON.parse(fs.readFileSync(FIXTURE_FILE, 'utf8'))
}

/**
 * Empty the rate-limit counters. Every spec signs in from 127.0.0.1, so a run
 * soon uses up the per-IP budget; the limits themselves have backend tests.
 */
export function resetRateLimits() {
  djangoShell('from django.core.cache import cache; cache.clear()')
}

/** Run Python in the backend's Django shell; returns what it prints. */
export function djangoShell(code) {
  return execFileSync(path.join(BACKEND, '.venv', 'Scripts', 'python.exe'), [
    'manage.py', 'shell', '-c', code,
  ], { cwd: BACKEND, env: CONSOLE_EMAIL_ENV, encoding: 'utf8' })
}

/** RFC 6238 authenticator code (SHA-1, 30-second steps) from a hex secret. */
export function totp(hexSecret, time = Date.now(), digits = 6) {
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(time / 1000 / 30)))
  const hmac = crypto.createHmac('sha1', Buffer.from(hexSecret, 'hex')).update(counter).digest()
  const offset = hmac[hmac.length - 1] & 0x0f
  const value = hmac.readUInt32BE(offset) & 0x7fffffff
  return String(value % 10 ** digits).padStart(digits, '0')
}

/** The hex secret behind a setup key as authenticator apps show it (base32, RFC 4648). */
export function hexFromSetupKey(setupKey) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const bits = [...setupKey.toUpperCase()].map((c) => alphabet.indexOf(c).toString(2).padStart(5, '0')).join('')
  const bytes = bits.match(/.{8}/g).map((byte) => parseInt(byte, 2))
  return Buffer.from(bytes).toString('hex')
}

/** A new browser context signed in as one demo account (its own cookies). */
export async function signedIn(browser, account) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto('/login')
  await page.locator('#email').fill(account.email)
  await page.locator('#password').fill(account.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  if (account.staff) await enterCode(page)
  await expect(page).not.toHaveURL(/\/login$/)
  return page
}

async function enterCode(page) {
  const secret = backendEnv('DEMO_TOTP_SECRET')
  if (!secret) throw new Error('Set DEMO_TOTP_SECRET in highground/backend/.env, then re-seed (see README).')
  const field = page.locator('#two-factor-code')
  await field.waitFor()
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await field.fill(totp(secret))
    await page.getByRole('button', { name: 'Verify and sign in' }).click()
    const done = await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 5000 })
      .then(() => true, () => false)
    if (done) return
    // Each code works once per account: if this one was just used, wait for the next.
    await page.waitForTimeout(31_000 - (Date.now() % 30_000))
  }
  throw new Error('Two-factor sign-in did not complete')
}

/** Call the API as the signed-in page, with its session cookie and CSRF token. */
export async function api(page, method, url, data) {
  const cookies = await page.context().cookies()
  const csrf = cookies.find((cookie) => cookie.name === 'csrftoken')?.value
  const response = await page.request.fetch(url, {
    method,
    data,
    headers: csrf ? { 'X-CSRFToken': csrf } : {},
  })
  if (!response.ok()) throw new Error(`${method} ${url} → ${response.status()}: ${await response.text()}`)
  return response.json()
}
