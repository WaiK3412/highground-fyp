/**
 * Before the run: reset the demo database with seed_demo --flush (anything
 * added by hand is lost), then note a village in the demo officer's district
 * where the demo resident has no case: duplicate rules compare cases within a
 * village by name, phone, pin and address, so a new request there is not flagged.
 */

import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { ACCOUNTS, BACKEND, CONSOLE_EMAIL_ENV, FIXTURE_FILE } from './helpers.js'

const PYTHON = path.join(BACKEND, '.venv', 'Scripts', 'python.exe')

function manage(...args) {
  return execFileSync(PYTHON, ['manage.py', ...args], { cwd: BACKEND, encoding: 'utf8', env: CONSOLE_EMAIL_ENV })
}

const FIND_VILLAGE = `
import json
from accounts.models import UserAccount
from cases.models import CaseRecord, LocationArea
officer = UserAccount.objects.get(email=${JSON.stringify(ACCOUNTS.officer.email)})
used = CaseRecord.objects.filter(submitted_by_user__email=${JSON.stringify(ACCOUNTS.resident.email)}).values_list("location_area_id", flat=True)
village = (LocationArea.objects.filter(level="village", parent_id=officer.district_id, active=True)
           .exclude(pk__in=used).order_by("code").first())
print(json.dumps({"villageCode": village.code}))
`

export default function globalSetup() {
  manage('seed_demo', '--flush')
  const output = manage('shell', '-c', FIND_VILLAGE).trim().split(/\r?\n/).pop()
  fs.writeFileSync(FIXTURE_FILE, output)
}
