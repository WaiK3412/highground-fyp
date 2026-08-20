# HighGround — frontend

The React single-page app for HighGround, a post-flood recovery coordination
platform (Coventry 6000CEM final-year project). The Django API it talks to
lives in `../backend`.

## Running it

Both halves must be up. The API is expected on `http://localhost:8000`.

```bash
# 1. database — needs Docker Desktop running
cd ../backend && docker compose up -d

# 2. backend — leave this terminal open
cd ../backend && .venv/Scripts/python manage.py runserver

# 3. frontend — a second terminal, also left open
npm install     # first time only
npm run dev
```

## How it is put together

- **Vite + React**, no router library yet — `App.jsx` switches screens on
  session state, because there are only three of them so far.
- **Session cookie auth, not JWT** (ADR-001). `api.js` fetches a CSRF token
  before the first POST and sends `credentials: 'include'` on every request.
- **No CSS framework.** `styles/tokens.css` and `styles/styles.css` are copied
  unchanged from the frozen design contract in `design-prototype-v2/`, so the
  ported screens inherit the v2 identity exactly. Do not restyle here — change
  the design contract first.
- **Screens are ported verbatim** from that contract, never redesigned.

## What is here

| Screen | File | Status |
|---|---|---|
| 02 Sign in | `pages/Login.jsx` | done |
| 03 Create account | `pages/Register.jsx` | resident path done; role application TODO |
| Case queue | `pages/CaseQueue.jsx` | done |
| 14 / 19 Admin | — | Django admin instead (ADR-002) |

Residents cannot yet submit a case (FR1) — that wizard is the next screen due.

## Checks

```bash
npm run lint
npm run build
```
