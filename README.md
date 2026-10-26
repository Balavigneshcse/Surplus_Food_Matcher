# AnnamSetu

Team **MIND MATRIX**. Surplus food in hostel kitchens, handled as one loop:

**PREDICT** (rule forecast P50/P90 from opt-outs) → **PREVENT** (cook card + one hot reserve vessel) →
**PRE-BOOK** (T-90 decision and NGO offers) → **PROVE** (SafeClock, FSSAI Schedule II batch record, QR) →
**ROUTE** (waste hierarchy enforced in code and in the database).

Stack: Python 3.12 · FastAPI 0.162 · SQLAlchemy 2.1 + psycopg 3 · PostgreSQL 17 (Docker) · Alembic ·
plain HTML/CSS/JS pages served from `static/`. The forecast is our own rule model (`RULE_V1`); no
pre-trained or open AI model is used. The full spec is `AnnamSetu_Build_Plan.md` (one folder up).
Gaps and choices made while building are in `docs/DECISIONS.md`.

All kitchens, NGOs, people and numbers in the demo data are **fictional sample data**.

## Build phases

| Phase | Scope | Status |
|---|---|---|
| 1 Setup & foundation | Project skeleton, settings, DB + 14 tables (Alembic 0001-0006), login/roles/CSRF, problem+json errors, demo clock + seeder + reset, shared JS/CSS, login and index pages, access-rule / migration / model-drift / constraint tests | **done** |
| 2 PREDICT + PREVENT | Rule forecast, cook card, slots/dishes setup, meals API, opt-out page, plan + cook card pages | next |
| 3 PROVE (SafeClock) | Lid + probe log, SafeClock rule, reserve panel | |
| 4 PRE-BOOK | T-90 rule, offers (partner + overflow), NGO inbox, scheduler steps | |
| 5 Handover + record | Handover, Schedule II record, label, QR, public record page, NGO fields 10-12 | |
| 6 ROUTE + dashboard + admin | Route log page, close meal, dashboard, admin setup page, CSV export | |

In Phase 1 every router already exists with its prefix and role/CSRF rule, but the feature endpoints
arrive with their phase. After logging in, `index.html` shows a welcome card until the role's home page
(`kitchen/plan.html`, `ngo/inbox.html`, `admin/setup.html`) exists.

## One-time setup (Windows 11)

You need: **Python 3.12** (`py -3.12 --version` should print 3.12.x), **Docker Desktop** (running), and
this folder. Open **PowerShell** in the `annamsetu` folder (the one with `requirements.txt`):

```powershell
# 1. Virtual environment + packages (pinned versions, plan 1.2)
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt

# 2. Your settings: copy the example, then edit .env in an editor
copy .env.example .env
.\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste as APP_SECRET_KEY
#    - DB_PASSWORD and the password inside APP_DATABASE_URL must be the same (no % sign in it)
#    - APP_DEMO_ADMIN_PASSWORD / _KITCHEN_ / _NGO_: 8-64 characters each (demo logins, see below)

# 3. Database: Postgres 17 in Docker on host port 5433, then create the 14 tables
docker compose up -d db
.\.venv\Scripts\python -m alembic upgrade head

# 4. Check everything works
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m uvicorn app.main:app --reload     # open http://localhost:8000
```

Always run tools as `.\.venv\Scripts\python -m ...` (`python -m alembic`, `python -m pytest`,
`python -m uvicorn`). This works without activating the venv and even when launchers such as
`alembic.exe` are blocked. VS Code / PyCharm: select `.venv\Scripts\python.exe` as the interpreter.
In **Git Bash** the same commands are `.venv/Scripts/python -m ...`.

### If something goes wrong

| Problem | Fix |
|---|---|
| `import sqlalchemy` fails: *"DLL load failed ... An Application Control policy has blocked this file"* | Install SQLAlchemy's pure-Python build (trap 10 in the plan): `$env:DISABLE_SQLALCHEMY_CEXT="1"; .\.venv\Scripts\python -m pip install --force-reinstall --no-deps --no-binary sqlalchemy sqlalchemy==2.1.6` |
| PowerShell refuses `Activate.ps1` | Don't activate; call `.\.venv\Scripts\python -m ...` as shown above. |
| `password authentication failed for user "annamsetu"` | The database volume keeps the password it was **first** created with. Put the old one back in `.env`, or wipe the dev DB: `docker compose down -v`, then `docker compose up -d db` and `alembic upgrade head` again. |
| `connection refused` on port 5433 | Start Docker Desktop, then `docker compose up -d db`. Check with `docker ps` (container `annamsetu-db`). |
| Integration tests fail to start a container | Testcontainers needs Docker Desktop running. Or point them at a database you can wipe: `$env:TEST_DATABASE_URL="postgresql+psycopg://..."` (never your dev DB). |
| A demo user can't log in | Users are created once, with the password `.env` had at that time. Changing `.env` later does not change them: run `docker compose down -v` (wipes all dev data) and start again. |
| Port 8000 busy | Add `--port 8001` to the uvicorn command. |

## Daily commands

```powershell
docker compose up -d db                                     # Postgres 17 on host port 5433 (Docker Desktop running)
.\.venv\Scripts\python -m alembic upgrade head              # apply new migrations after a pull
.\.venv\Scripts\python -m uvicorn app.main:app --reload     # dev server: http://localhost:8000  (API docs: /docs)
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # demo on the hotspot (no --reload)
.\.venv\Scripts\python -m pytest -m "not integration"       # fast: unit + API tests (no database)
.\.venv\Scripts\python -m pytest -q                         # everything; integration tests start a throwaway postgres:17
.\.venv\Scripts\python -m alembic current                   # which revision the dev DB is on (0006 = head)
.\.venv\Scripts\python -m alembic downgrade base; .\.venv\Scripts\python -m alembic upgrade head   # re-check migrations (drops all dev data)
docker exec -it annamsetu-db psql -U annamsetu -d annamsetu # psql without installing it
docker compose stop db                                      # stop the database, keep the data
docker compose down -v                                      # wipe the local DB (dev only)
```

- Always run **one** uvicorn worker: the scheduler and the demo clock live inside the app process.
- Stop the server with **Ctrl+C**.
- Never edit a merged migration; add a new revision (`--rev-id 0007`) instead. Tests fail if the
  models and the migrations drift apart (`tests/integration/test_migrations.py`).

## Demo mode (dev only)

With `APP_DEMO=true` in `.env` the app, at startup:
- seeds the sample data (idempotent; uses today's IST date),
- uses the demo clock, shows the **SAMPLE DATA** banner, and
- enables the ADMIN-only demo API: `GET/POST/DELETE /api/admin/demo/clock` (read, set `{at}` or jump
  `{plusMinutes}`, back to real time) and `POST /api/admin/demo/reset` (TRUNCATE the meal/batch/offer
  tables, reseed today, clock to 08:30). Examples: `docs/api.http`.

**Demo logins** (local development only; set in `.env`, hashed at startup, never put them on slides):

| Username | Role | Password (from `.env`) |
|---|---|---|
| `admin` | ADMIN | `APP_DEMO_ADMIN_PASSWORD` |
| `kitchen` | KITCHEN (Sample Hostel Mess, code MESS1) | `APP_DEMO_KITCHEN_PASSWORD` |
| `ngo` | NGO (Sample NGO A) | `APP_DEMO_NGO_PASSWORD` |

Choose your own values in your local `.env` (never commit `.env`; this repo is public).

Log in at `http://localhost:8000/login.html`. Users are created only once; if you change a password in
`.env` later, run `docker compose down -v` (or change it from the admin page once it exists).

Sample data: kitchen MESS1 "Sample Hostel Mess" (1,000 registered), LUNCH 12:00-14:00 and DINNER
19:30-21:30 (rescue off), dishes Rice (reserve, 200 g cooked / 82 g raw), Sambhar 150 g, Poriyal 80 g,
four fictional verified NGOs with MoUs ("Sample NGO A-D"; D has no reheating and fails the offer
filters), today's lunch with 44 opt-outs, and yesterday's dinner reserve batch that is RED.

On the demo laptop set `APP_PUBLIC_BASE_URL=http://192.168.137.1:8000` (Windows Mobile Hotspot) so the
phones can open QR links; see `docs/demo-script.md`.

## Tests

| Folder | What | Needs |
|---|---|---|
| `tests/unit/` | clock, demo clock, settings, schema helpers (later: the pure rules) | nothing |
| `tests/api/` | role rules per router prefix (401/403), every real `/api` route carries its prefix rule + CSRF, CSRF on POST/PUT/DELETE (login and logout too), session cookie settings, dummy-hash check for unknown/disabled users, bcrypt's 72-byte rule, problem+json shape, unknown `/api` path 404 for every method, static files, health, error handlers, lifespan + scheduler jobs, demo clock API | nothing |
| `tests/integration/` | migrations (one head, downgrade/upgrade, models = migrations incl. CHECK and partial-index text, ids `generated always`, every timestamp a timestamptz), DB constraints and the append-only trigger, UTC sessions + optimistic lock, login against the DB (real session cookie: flags, holds only ids, forged cookie ignored), demo seeder (IST date after midnight, sample labels)/reset/demo API, opt-out purge | Docker (Testcontainers `postgres:17`) or `TEST_DATABASE_URL` |

## Project layout

```
app/main.py         app assembly: lifespan, middleware, error handlers, routers, static mount (last)
app/scheduler.py    15-second loop tick (steps added in later phases) + nightly opt-out purge
app/core/           config (Settings), db (Base, SessionLocal, get_db), clock, security, errors
app/models/         the 14 tables (mirror the Alembic migrations; never create tables)
app/schemas/        Pydantic v2 request/response models (camelCase JSON via ApiModel)
app/rules/          pure business rules (no FastAPI, no DB)
app/services/       service functions (load data, call rules, commit)
app/routers/        one router per feature; role + CSRF rules are one line per router
app/demo/           DemoClock, seeder, demo router (APP_DEMO=true only)
alembic/versions/   0001 ... 0006, written by hand
static/             pages, css, js (api.js, ui.js, i18n.js), vendor/chart.umd.min.js (Chart.js 4.5.1)
tests/              unit/, api/ (TestClient, no DB), integration/ (Testcontainers postgres:17)
docs/               DECISIONS.md, demo-script.md, safeclock-sop.md, api.http
```

## Rules of the codebase (short)

- Plain `def` endpoints; sync SQLAlchemy 2.x (`Mapped`, `mapped_column`, `select()`).
- Never call `datetime.now()` in business code: use the injectable clock (`ClockDep` / `get_clock()`).
- Weights are integer grams; temperatures are `Decimal`; times are stored as UTC and shown in IST.
- Errors are `application/problem+json` with a `code` field (400 validation, 401, 403, 404, 409).
- Every POST/PUT/DELETE needs the `X-CSRF-Token` header (`static/js/api.js` does this for you).
- Never edit a merged migration; add a new revision instead.
