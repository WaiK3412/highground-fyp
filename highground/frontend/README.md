# HighGround — frontend

The React single-page app for HighGround. It talks to the Django API in
`../backend` (expected on `http://localhost:8000`). Setup, demo data and the
full feature list are in the [main README](../../README.md).

```powershell
npm install
npm run dev      # http://localhost:5173
```

## How it is put together

- **Vite + React, no router library.** `src/App.jsx` picks the screen from the
  signed-in user's role and the current screen name held in state. An
  administrator is sent to Django Admin instead of an app screen.
- **Session cookie and CSRF, not tokens.** `src/api.js` fetches a CSRF token
  before the first write and sends the session cookie with every request.
  Hiding a button is never the security check; the API enforces every rule.
- **Styles.** `src/styles/tokens.css` and `styles.css` come from the design
  prototype; app additions live in `src/styles/app.css`. No CSS framework.
- **Shared pieces.** `pages/ResidentShell.jsx` and `pages/ResponderShell.jsx`
  draw the role sidebars; `src/useLoad.js` loads a list and handles retry;
  `src/components/` holds the parts of the larger screens.

## Screens

| Screen | File | Who |
|---|---|---|
| Sign in / create account | `pages/Login.jsx`, `pages/Register.jsx` | Everyone |
| My Recovery (cases, detail, reply, confirm work) | `pages/ResidentDashboard.jsx`, `components/resident/` | Resident |
| Submit a request (five steps, map pin) | `pages/SubmitRequest.jsx`, `components/request/`, `pages/PinPicker.jsx` | Resident |
| Supplies needed / supply appeals | `pages/SupplyAppeals.jsx` | Resident reads; NGO posts |
| Profile | `pages/Profile.jsx` | Resident |
| Case queue (list and map, case panel) | `pages/CaseQueue.jsx`, `pages/CaseMap.jsx`, `components/queue/` | Officer, NGO |
| Task board | `pages/TaskBoard.jsx`, `components/tasks/` | NGO |
| Duplicate review | `pages/DuplicateReview.jsx` | Officer |
| How priority works | `pages/PriorityRules.jsx` | Officer, NGO |
| Notifications | `pages/Notifications.jsx` | Everyone signed in |

## Checks

```powershell
npm test         # Node's built-in test runner: src/tests/*.test.js
npm run lint     # oxlint
npm run build
```
