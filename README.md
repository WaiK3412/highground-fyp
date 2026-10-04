# HighGround

HighGround is a post-flood recovery coordination platform, built as a final-year
project. Households ask for recovery help, district disaster officers check and
prioritise the requests, and NGOs claim the work and report progress, all on one
shared record of each case. It is an academic prototype for local demonstration,
not a production deployment.

## What each role can do

| Role | Main features |
|---|---|
| **Resident** (household) | Register; submit a recovery request in five steps (household, home and damage, safety and needs, photos, review) with a village and a map pin; follow each case's status, priority class and the reasons for it; answer an officer's request for more information; confirm finished work, or report it incomplete, for each type of help, with the responder's before/after photos; see supplies NGOs are asking for; notifications; profile. |
| **Disaster officer** | Case queue as a list or map with filters; verify, ask for more information or reject; change a priority class with a reason the household can see; review possible duplicates side by side; see help no organisation has taken yet; close finished work when the household cannot confirm, with a recorded reason. |
| **NGO responder** | Case queue; claim one type of help (a "job") on a case; release it; task board with one accountable lead per task, a safety acknowledgement before starting, progress notes and before/after photos; mark work complete; post supply appeals with a drop-off point. |
| **Administrator** | Django Admin: approve or reject officer and NGO role applications, manage accounts and reference data, correct a case's location. |

## How it works

- **Frontend:** a React single-page app (Vite). Screens call the API through
  `src/api.js`, which sends the session cookie and CSRF token.
- **Backend:** Django REST Framework views check permissions and validate input,
  then call services that change the database inside transactions.
- **Database:** PostgreSQL. Every status change writes a row to an append-only
  event log, which also feeds the case history and notifications.
- **Priority (classes-1.0):** class 1 Health-critical (someone needs urgent
  medical attention or medical needs are disrupted), class 2 At risk (an older
  person, a child under 5, a person with a disability or medical needs, a single
  parent, or a home that is hard to reach), class 3 Standard. Cases are served
  by class, then in submission order. Each case stores the reasons and the rules
  version. The rules are a pure Python module with no database code.
- **Duplicates (rules-1.0):** each new request is compared with the live cases
  in its village using plain rules (for example the same house or lot number
  and address). A match is only a flag; an officer decides.
- **Claiming:** each type of help on a case is a separate job. A claim locks the
  case and job rows (`select_for_update`), so two organisations cannot win the
  same job.

## Security and privacy

- Session authentication with CSRF protection; every API endpoint declares its
  permission policy, and each role's access is covered by tests.
- Residents see only their own cases. The exact address and map pin are shown
  only to district staff and to an organisation holding an active job on the
  case; other NGOs see the village only.
- Uploaded photos are re-encoded with location metadata removed, stored under
  generated names, and served only through a permission-checked endpoint.
- The event log cannot be edited or deleted through the app.
- Login is limited to 10 requests per minute per IP, registration to 5.
- Debug mode is off unless `DJANGO_DEBUG=1`; the demo data command refuses to
  run without it.

## Repository layout

```
highground/
  backend/    Django project, REST API, PostgreSQL configuration and tests
  frontend/   React/Vite single-page application
```

## Code map

Paths are relative to `highground/backend` unless noted.

| Responsibility | Start here |
|---|---|
| Priority classes and their reasons | `priority/classes.py` |
| Duplicate rules | `cases/duplicate_rules.py`; shared normalisation in `cases/normalise.py` |
| Database changes (transactions, audit rows) | `cases/services.py`; duplicate scan and review in `cases/duplicate_services.py` |
| Role and household privacy rules | `accounts/permissions.py` |
| Data, validation and JSON shapes | `cases/models.py`, `accounts/models.py`; `cases/serializers/` by topic (cases, submission, tasks, decisions, notifications, duplicates, appeals), matching `cases/views/` |
| Photo cleaning | `cases/images.py` (Pillow) |
| API views by topic | `cases/views/` (cases, verification, jobs, tasks, duplicates, notifications, appeals); routes in `config/urls.py` |
| Screens | `highground/frontend/src/pages/`; parts of larger screens in `src/components/` (`queue/`, `request/`, `resident/`, `tasks/`, `CaseFacts.jsx`) |
| Shared frontend helpers | `highground/frontend/src/api.js`, `useLoad.js` (loading and retry), `initials.js`, `icons.jsx` |
| Styles | `highground/frontend/src/styles/`: `tokens.css` and `styles.css` from the design prototype, `app.css` for app additions |

### Reading the code

Follow one case from start to finish:

1. **Submit:** `pages/SubmitRequest.jsx` → `src/api.js` → `CaseListView.create`
   in `cases/views/cases.py` → `CaseCreateSerializer` in
   `cases/serializers/submission.py`.
2. **Verify:** `components/queue/CaseActions.jsx` → `cases/views/verification.py`
   → `classify_case_record` in `cases/services.py` → `classify` in
   `priority/classes.py` (priority is set only when an officer verifies).
3. **Claim:** `claim_job` in `cases/views/jobs.py` (the locking claim).
4. **Do the work:** `cases/views/tasks.py`, `pages/TaskBoard.jsx`.
5. **Confirm or close:** `components/resident/CompletionDecision.jsx`, then
   `close_on_behalf` for the officer route.

The tests for each step (`cases/tests/test_submission.py`, `test_lifecycle.py`,
`test_jobs.py`, `test_tasks.py`, `test_close_on_behalf.py`) state each rule as
a sentence.

## Run locally

Prerequisites: Python 3.12+, Node.js 20+, Docker Desktop (for PostgreSQL).

### 1. Database

Copy `highground/backend/.env.example` to `highground/backend/.env` and replace
every placeholder with local values (use `DJANGO_DEBUG=1` and `DB_PORT=5433`).
Never commit `.env`. Then:

```powershell
cd highground/backend
docker compose up -d
```

### 2. Backend

```powershell
cd highground/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API runs at `http://127.0.0.1:8000/`; Django Admin is at `/admin/`.

### 3. Demo data (optional)

```powershell
python manage.py seed_demo --flush
```

This creates demo organisations, accounts and cases, and prints the demo logins.
`--flush` deletes existing demo data first. It only runs with `DJANGO_DEBUG=1`,
because the demo accounts share a known password (defined in
`cases/management/commands/seed_demo.py`).

### 4. Frontend

In a second terminal:

```powershell
cd highground/frontend
npm install
npm run dev
```

Open the URL Vite prints (normally `http://localhost:5173`).

### Email (optional)

With `EMAIL_HOST` unset, notification emails are printed in the backend
terminal. To send real mail, fill the email values in `.env` (examples in
`.env.example`):

| Provider | `EMAIL_HOST` | `EMAIL_PORT` | `EMAIL_HOST_USER` | `EMAIL_HOST_PASSWORD` | `DEFAULT_FROM_EMAIL` |
|---|---|---|---|---|---|
| Brevo | `smtp-relay.brevo.com` | `587` | SMTP login from SMTP & API | SMTP key, not API key | `HighGround <your verified sender address>` |
| Gmail | `smtp.gmail.com` | `587` | Your full Gmail address | App Password | `HighGround <the same Gmail address>` |

See Brevo's
[SMTP setup instructions](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP)
or [Google's App Password instructions](https://support.google.com/mail/answer/185833?hl=en).
Check delivery with `python manage.py send_test_email you@example.com`, and restart
the backend after changing settings. Demo `@hg.my` accounts are skipped
(`EMAIL_SKIP_DOMAINS=hg.my`); to receive demo mail, set `DEMO_RESIDENT_EMAIL` /
`DEMO_OFFICER_EMAIL` before running `seed_demo --flush`.

## Tests

Backend, from `highground/backend`:

```powershell
python manage.py test
```

Tests use a fast password hasher (`config/test_runner.py`); the app itself keeps
Django's default.

Frontend, from `highground/frontend`:

```powershell
npm test         # API client and initials helper tests
npm run lint
npm run build
```

## Main API routes

| Area | Routes |
|---|---|
| Accounts | `GET /api/auth/csrf/`, `POST /api/auth/register/`, `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET/PATCH /api/auth/me/` |
| Cases | `GET/POST /api/cases/`, `GET /api/cases/<id>/`, `GET /api/cases/stats/`, `GET /api/cases/map/`, `GET /api/locations/` |
| Officer decisions | `POST /api/cases/<id>/verify/`, `/priority-override/`, `/close/`; resident answer `POST /api/cases/<id>/reply/` |
| Jobs | `POST /api/jobs/<id>/claim/`, `/release/`, `/complete/`, `/confirm/`; `GET /api/jobs/unmet/` |
| Tasks | `GET /api/tasks/`, `GET/POST /api/cases/<id>/tasks/`, `PATCH /api/tasks/<id>/`, `POST /api/tasks/<id>/photos/` |
| Duplicates | `GET /api/duplicates/`, `GET /api/duplicates/<id>/`, `POST /api/duplicates/<id>/decide/` |
| Other | `/api/notifications/`, `/api/appeals/`, `/api/drop-off-points/`, `/api/priority-rules/` |

## Not included

- Password reset, an AI assistant, aid-package tracking, volunteer sign-up and
  in-app pledges of goods (NGO supply appeals replace pledges).
- Production deployment (HTTPS hosting, real host settings, backups).
- Real email delivery needs SMTP settings (see Email above).
