# Decisions log

Gaps or contradictions found while building, and the simplest choice made. Newest phase at the bottom;
append, never rewrite.

## Phase 0-1 (foundation), 26 Oct 2026

1. **"Our own model, not an open model."** The forecast is the team's own rule model (`RULE_V1`, plan 8.1)
   behind the `Forecaster` protocol. No pre-trained or open-source AI model is used anywhere. The Phase 2
   ML forecaster will be trained by the team on its own mess data (scikit-learn only as a library).
2. **Postgres host port 5433** (plan 11.2 shows 5432). `compose.yaml`, `.env.example` and the local `.env`
   use `localhost:5433`. The compose project is pinned to `name: annamsetu` and the volume to
   `annamsetu_pgdata`.
3. **How CHECKs are written in migrations.** Single-column CHECKs sit inside `op.create_table` as
   `sa.CheckConstraint` (exactly like the plan's 0003 example); multi-column CHECKs, the route-log rule
   CHECKs, the partial unique indexes and the append-only trigger use `op.execute`. The models declare the
   same CHECKs and indexes by name; `test_migrations.py` checks columns/types/indexes/uniques/FKs with
   Alembic's `compare_metadata` and compares CHECK names table by table.
4. **Every constraint has an explicit name** (`uq_*`, `ck_*`, `ux_*`, `ix_*`) so `core/errors.py` can map
   an `IntegrityError` to a `code` (e.g. `ck_cattle_raw_veg_only` -> `CATTLE_FEED_RAW_VEG_ONLY`,
   `ux_offer_one_taker` -> `OFFER_NOT_OPEN`). Unknown names answer 409 `CONSTRAINT_VIOLATED`.
5. **Small sanity CHECKs added beyond section 5** (all consistent with section 8): kitchen counts/radius > 0
   and `side_dish_basis` list; NGO capacity/min batch > 0, `open_to > open_from` (no overnight windows in
   the MVP), phone needs `phone_consent_at` (DPDP), `0 <= pickups_on_time <= pickups_total`; slot
   share at T-90 in (0, 1] (it is a divisor), buffer/cutoff/pickup offset >= 0; meal `p90 >= p50`,
   MANUAL needs `override_reason`, CLOSED needs `actual_diners`; meal_dish amounts >= 0; reserve batch
   `prepared_at <= lidded_at`, ACCEPTED/HANDED_OVER need `accepted_ngo_id`, TO_DISPOSE needs
   `dispose_reason`; offer `expires_at > sent_at`, `qty_g > 0`; batch record: GREEN <=> `refrigerate_by`
   set, fields 10-12 all-or-nothing, `qty_distributed_g <= qty_donated_g`, handover colour GREEN/AMBER only.
6. **`created_at` columns have `server_default now()`** as an audit fallback. Business timestamps
   (`read_at`, `sent_at`, `logged_at`, ...) have no default and always come from the app clock; the seeder
   also passes `clock.now()` for `created_at`.
7. **Column choices the plan left open:** `offer.channel` CHECK allows only `IN_APP` (the WhatsApp
   revision adds a value); `batch_record.mou_ref` is NOT NULL (offers only go to NGOs with an MoU);
   `meal.created_by` is NOT NULL; `meal.attendance_ratio`/`buffer_pct` are NOT NULL snapshots copied from
   the slot when the meal is created; `p50`/`p90`/`line_g`/`reserve_g` stay NULL while a meal is PLANNED
   (computed live) and are frozen at issue; version columns default to 1.
8. **Sample NGOs: four, as in plan 11.4** (the task text said 2-3): Sample NGO A (standing partner),
   B and C (pass the offer filters), D (verified, MoU, but no reheating, so it fails the filters). All are
   fictional, with fake 14-digit FSSAI numbers and no phone numbers.
9. **Sample dinner slot ratio 0.500**, so yesterday's dinner forecast is P50 500 / P90 530 and its reserve
   vessel is exactly 6.0 kg, matching the demo script (3:40, "reserve unsafe 6 kg -> BIOGAS").
10. **Yesterday's dinner batch is seeded already TO_DISPOSE with worst colour RED** (`SAFECLOCK_RED`),
    with its last hot reading at 20:15 yesterday. The scheduler's SafeClock step arrives in a later phase;
    this is exactly the state that step would produce, so the route page can use it.
11. **Seeder details:** opt-outs (SAMPLE-001 ... SAMPLE-044) are created only together with today's
    lunch; existing rows are never updated (a changed `.env` password does not overwrite a user); a demo
    user whose `APP_DEMO_*_PASSWORD` is missing or not 8-64 characters is skipped with a warning (and
    without the kitchen user no sample meals are created).
12. **Demo reset also zeroes NGO pickup counters** (`pickups_total`, `pickups_on_time`) so every demo
    starts with the same on-time scores. Order: clock back to real time -> TRUNCATE -> reseed -> clock to
    08:30 today.
13. **Demo router** lives at `/api/admin/demo` (ADMIN + CSRF, demo mode only) and adds
    `GET /api/admin/demo/clock` (read the demo time and offset) for the admin panel, next to the planned
    `POST`/`DELETE /clock` and `POST /reset`. Outside demo mode the router is not mounted at all.
14. **Auth responses:** login answers `{role, displayName, csrfToken}`; logout needs only the CSRF token
    (table 6 says "public / any"). `/api/me` also returns `id`, `username`, `displayName`,
    `kitchenCode`/`kitchenName` and `ngoName` for the page header.
15. **Validation errors never echo the submitted values** (`input` is removed from `errors`), so a
    password can't come back in a 400. Unexpected exceptions answer problem+json 500 `INTERNAL_ERROR`.
    `/api/health` answers 503 `DB_UNAVAILABLE` when the database is unreachable.
16. **Router placeholders:** every router of section 9 exists with its prefix and role/CSRF dependencies
    but no endpoints. `app/main.py` names the router list `API_ROUTERS` so the access-rule tests can
    check that every router is classified; those tests copy each router (same prefix + dependencies) with
    probe endpoints to prove 401/403/CSRF per prefix.
17. **index.html** redirects each role to its home page only if that page exists (HEAD check). Until the
    later phases add `kitchen/plan.html`, `ngo/inbox.html` and `admin/setup.html`, it shows a welcome card
    (name, role, kitchen/NGO, server time) with a logout button instead of a 404.
18. **login.html and index.html use inline module scripts**, because the plan's JS list has no
    `login.js`/`index.js` ("one JS file per page" applies to the feature pages).
19. **The nightly opt-out purge is implemented now** (`services/opt_outs.purge_old`), because the cron job
    is already wired in `lifespan`; `STEPS` of the loop tick stays empty until later phases.
20. **SQLAlchemy is installed as its pure-Python build** on this laptop (Application Control blocks the
    compiled modules; plan trap 10). No other package needed a fallback.

## Phase 1 completion audit, 26 Oct 2026

Checked every Phase 1 item (plan 1.2, 1.3, 2, 5, 9, 11) against the code. The 14 tables, every column,
default, CHECK, unique constraint, partial unique index, the probe-log trigger and all six downgrades
already matched section 5; the changes below close the remaining gaps.

21. **Model/migration drift test made complete.** Alembic's `compare_metadata` (now also with
    `compare_server_default=True`) cannot see inside a CHECK condition or the WHERE of a partial index
    (verified: changing either in a model still gave `[]`). `test_migrations.py` therefore adds each
    model CHECK and index to a temporary `LIKE` copy of the migrated table (inside a rolled-back
    transaction) and compares Postgres's own `pg_get_constraintdef` / `pg_indexes.indexdef` output with
    the real table. This is not `create_all()`: no table is built from the models. A mutation check
    (changed CHECK text, changed predicate, dropped `unique`) makes the tests fail as intended.
    `test_migrations.py` also walks the revisions down one step at a time and back up, and checks that
    every constraint name in `core/errors.CONSTRAINT_CODES` exists in the database.
22. **More constraint codes** in `core/errors.py` for safety rules later phases will hit:
    `TEMP_OUT_OF_RANGE`, `P90_BELOW_P50`, `OVERRIDE_NEEDS_REASON`, `ACTUAL_DINERS_REQUIRED`,
    `BATCH_NO_TAKEN`, `DISTRIBUTION_INCOMPLETE`. Any other name still answers 409 `CONSTRAINT_VIOLATED`.
23. **`UTC_CONNECT_ARGS`** (`core/db.py`) holds the `-c timezone=UTC` connection option; the integration
    tests build their engine from the same constant, so they test the app's real session setting.
24. **App log lines are visible under uvicorn.** uvicorn configures only its own loggers, so
    "demo data seeded ..." and "scheduler started ..." were silently dropped. `main.py` gives the `app`
    logger one console handler at INFO (APScheduler's own per-run INFO lines stay hidden).
25. **New Phase 1 tests:** clock (aware IST, IST date, `use_clock` swap), settings defaults, schema
    helpers (camelCase, naive = IST, IST output, temperature as a JSON number and its range), health 503,
    lifespan registers exactly the tick (interval, `max_instances=1`, `coalesce=True`) and the 02:30
    purge and shuts the scheduler down, no scheduler when disabled; integration: UTC round trip,
    `get_db` never commits, optimistic lock on `meal` and `reserve_batch` (StaleDataError and HTTP 409
    `CONCURRENT_EDIT`), demo mode end to end (seeded users log in, `/api/me` sampleData, demo router
    ADMIN-only + CSRF, reset over HTTP), lifespan seeds once in demo mode and not otherwise.
26. **Ports from plan 2.2 are not declared yet.** `Forecaster`/`Forecast` (rules/forecast.py) and
    `NotificationChannel`/`InAppChannel` (services/notify.py) arrive with the forecast and offers phases:
    `ForecastInput` is not specified until 8.1, and Phase 1 must not implement forecast or offer code.
    Their files exist as stubs, as do all other later-phase rules/services/schemas.
27. **Unknown `/api/...` paths:** GET answers problem+json 404 (`HTTP_404`) as planned. Other methods
    answer problem+json 405 (`HTTP_405`), because the static mount at `/` only allows GET/HEAD. A
    catch-all `/api/{path}` route was not added: it would also turn a real 405 (e.g. POST `/api/health`)
    into a 404.
28. **`/api/admin/...` in Phase 1:** the admin router has no endpoints yet, so a KITCHEN user asking for
    e.g. `/api/admin/kitchens` gets 404 (no such route) until the admin phase. The role rule is proven on
    the demo router (`/api/admin/demo/clock`: KITCHEN/NGO 403, ADMIN 200) and by the per-prefix probe
    tests in `tests/api/test_access_rules.py`.
29. **Smoke test (demo mode, port 8000, fresh cookie jars):** `/api/health` 200, `/login.html` and `/`
    200, `/docs` 200, `/api/auth/csrf` then login 200 for admin/kitchen/ngo with the right role in
    `/api/me` (sampleData true), KITCHEN and NGO 403 on `/api/admin/demo/clock`, POST without CSRF 403
    `CSRF_INVALID`, `/api/x` 404 problem+json, clock jump/set/reset and demo reset 200, logout 204 then
    `/api/me` 401. The server was stopped afterwards; the dev DB container stays up.
30. **Chart.js vendor copy** (`static/vendor/chart.umd.min.js`, v4.5.1 UMD, 208,522 bytes) keeps its
    `sourceMappingURL` comment; the `.map` file is not shipped, which only affects DevTools, not the page.

## Phase 1 adversarial verification, 26 Oct 2026

An independent re-check of the Phase 1 report (nothing taken on trust). Baseline before any change:
192 passed, 0 failed, as reported.

31. **Schema re-checked from the database catalog, not from the drift test.** A scratch script read
    `information_schema` / `pg_constraint` / `pg_indexes` / `pg_trigger` of the dev DB at 0006 and
    compared every column (type, length, precision/scale, nullability, server default, identity) and
    every FK with the models, then by eye with plan section 5: **0 differences**. All 14 tables, all
    ids `bigint generated always as identity`, every timestamp a `timestamptz`, both FSSAI 14-digit
    CHECKs, the three partial unique indexes, the four route-log CHECKs, the append-only trigger and
    both `version` columns are as planned. Migrations 0001-0006 were **not edited**. Dev DB:
    `downgrade base` (only `alembic_version` left, `forbid_change` gone) and `upgrade head` ran clean
    again; `alembic upgrade head --sql` also prints `like 'RESERVE%'` correctly.
32. **Unknown `/api/...` paths now answer 404 for every method** (supersedes #27). `main.py` mounts
    `StaticPages`, a small `StaticFiles` subclass: a path under `/api` that reaches the static mount
    matched no endpoint, so it answers problem+json 405 (with an `Allow` header) when that path exists
    with other methods (e.g. `POST /api/health`), otherwise 404 (`POST /api/x` was 405 before).
33. **FastAPI 0.162 keeps included routers whole.** `app.routes` lists one `_IncludedRouter` per
    `include_router`, not the endpoints, so code that walks `app.routes` looking for `APIRoute`s
    silently finds nothing. Both `StaticPages` and the new route-rule test use FastAPI's own
    `fastapi.routing.iter_route_contexts(...)` (the same helper its OpenAPI generator uses).
34. **The dummy bcrypt hash is made at startup** (`lifespan` calls `dummy_hash()`). Before, the first
    login with an unknown username paid for creating it (one extra bcrypt hash), so it was about twice
    as slow as any other failed login.
35. **New tests** (all pass; each security test was also run against a deliberately broken copy of the
    code and failed as it should): every real `/api` route carries its prefix role rule and CSRF
    (guards later phases); real `SessionMiddleware` settings (cookie name, `lax`, 12 h, `Secure` =
    `APP_SECURE_COOKIES`); `XSRF-TOKEN` gets `Secure` in prod; logout needs CSRF, deletes both cookies,
    kills the old token and the next page gets a new one; unknown and disabled users run exactly one
    bcrypt check on the dummy hash; a password over 72 bytes (also 25 Tamil letters = 75 bytes) never
    reaches bcrypt, 72 bytes still works, and bcrypt itself raises above 72; static files served
    without login; unknown `/api` path 404 for GET/HEAD/POST/PUT/DELETE and 405 + `Allow` for a known
    path. Integration: the real session cookie is HttpOnly, SameSite=Lax, Path=/, Max-Age=43200, not
    Secure in dev, holds exactly `{uid, csrf}`, a cookie with an edited `uid` is ignored (401); each
    login issues a new token; every `id` is identity ALWAYS; every timestamp is timestamptz; at
    00:30 IST (still the previous day in UTC) the seeder uses the IST date; everything seeded is
    labelled sample (names, addresses, `MOU-SAMPLE-*`, `SAMPLE-nnn` hostel IDs, no phone numbers);
    demo reset restarts ids (meals are #1 and #2 again) and keeps orgs/users.
36. **Correction to the earlier report:** the later-phase test files (`test_offer_race.py`,
    `test_scoping.py`, `test_full_loop.py`, the unit rule tests) and the feature pages (`kitchen/`,
    `ngo/`, `admin/`, `optout`, `record`, `dashboard`) do not exist yet at all; they were described as
    stubs. They belong to later phases; `index.html` already copes with a missing home page (#17).
    Ports from plan 2.2 are still deferred (#26): the task for this phase says to leave
    `rules/forecast.py` and `services/notify.py` as stubs.
37. **Smoke test (demo mode, port 8000, a fresh client per user, 53 checks, all passed):** health,
    `/`, `/index.html`, `/login.html`, `/docs`, `/openapi.json`, css/js/Chart.js 200; `GET` and `POST`
    `/api/x` 404 problem+json; `POST /api/health` 405; anonymous `/api/me` and demo clock 401; login
    without CSRF 403; wrong password, unknown user and a 73-byte password 401 `BAD_CREDENTIALS`;
    admin/kitchen/ngo log in (new token, HttpOnly + Lax + 12 h cookie, right role, sampleData true);
    kitchen/ngo 403 on GET and POST demo clock; admin clock jump/set (IST)/bad body 400/reset and demo
    reset (08:30, admin still logged in); logout without CSRF 403, logout 204, then 401 and a new token.
    After the reset the dev DB holds 1 kitchen, 4 NGOs, 3 users, 2 meals (ids from 1), 44 opt-outs and
    3 probe readings. uvicorn was stopped (port 8000 free); the `annamsetu-db` container is still up.
