import path from 'node:path'
import { defineConfig } from '@playwright/test'
import { CONSOLE_EMAIL_ENV } from './e2e/helpers.js'

// End-to-end tests drive the real app in Chrome against the demo database.
// They reset it first (e2e/global-setup.js), so run them one at a time.
// A backend you already started is reused as it is: stop it first if it sends real email.
const PYTHON = path.join('.venv', 'Scripts', 'python.exe')

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.spec.js',
  globalSetup: './e2e/global-setup.js',
  workers: 1,
  timeout: 90_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'chrome',  // the Chrome already installed; no separate browser download
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `${PYTHON} manage.py runserver 127.0.0.1:8000`,
      cwd: '../backend',
      env: CONSOLE_EMAIL_ENV,
      url: 'http://127.0.0.1:8000/api/auth/csrf/',
      reuseExistingServer: true,
    },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173/', reuseExistingServer: true },
  ],
})
