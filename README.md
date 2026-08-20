# HighGround

HighGround is a flood-recovery coordination platform developed as a final-year project. Residents can register and track aid requests; disaster officers verify requests; NGOs view and claim verified cases; administrators manage users through Django Admin.

## Current implementation

- Django REST Framework backend with PostgreSQL and session authentication.
- React + Vite frontend with login, registration, and role-aware case queue screens.
- Account roles, permission classes, and a verification workflow for officer/NGO applications.
- Case lifecycle API with an append-only event log and atomic NGO case claiming.
- Explainable priority-scoring engine with rubric models and automated tests.

## Repository layout

```
highground/
  backend/    Django project, REST API, PostgreSQL configuration, and tests
  frontend/   React/Vite single-page application
```

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop (for PostgreSQL)

## Run locally

### 1. Start PostgreSQL

Create `highground/backend/.env` with local-only values:

```env
SECRET_KEY=replace-with-a-long-random-development-secret
POSTGRES_DB=highground
POSTGRES_USER=highground
POSTGRES_PASSWORD=replace-with-a-local-password
DB_HOST=localhost
DB_PORT=5433
```

Then start the database:

```powershell
cd highground/backend
docker compose up -d
```

### 2. Start the backend

```powershell
cd highground/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API runs at `http://127.0.0.1:8000/`; Django Admin is at `/admin/`.

### 3. Start the frontend

In a second terminal:

```powershell
cd highground/frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`).

## Test

Run the backend suite from `highground/backend`:

```powershell
python manage.py test
```

Run a frontend production build from `highground/frontend`:

```powershell
npm run build
```

## Main API routes

- `GET /api/auth/csrf/`
- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `GET /api/cases/`
- `POST /api/cases/<id>/claim/`
- `POST /api/cases/<id>/verify/`

## Status

This is an in-progress academic prototype, intended for local development and demonstration rather than production deployment.
