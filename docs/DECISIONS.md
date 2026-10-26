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

## Phase 2 (PREDICT + PREVENT, module M1), 26 Oct 2026

The two uncommitted drafts from the interrupted attempt (`rules/forecast.py`, `rules/cook_card.py`) were
checked line by line against plan 8.1/8.2 and kept: the maths (Decimal `ROUND_HALF_UP`, P90 =
min(eligible, ceil(P50 x (1 + buffer/100))), the three dish cases, raw kg only when raw g/diner is set)
was right. Added: `manual_forecast()` (MANUAL), `DishInput.is_veg` and `menu_problem()` (exactly one
reserve dish, and it is veg), and unit tests for both files. This closes #26 for the `Forecaster` port.

38. **Demo numbers: the seeder keeps 44 opt-outs** (plan 11.4 and the demo script 11.6, 0:00 -> P50 813 /
    P90 862). The student's opt-out on stage (0:40) makes 45 -> **P50 812 / P90 861**: rice 70.6 kg raw,
    serving line 162.4 kg, reserve vessel 9.8 kg; sambhar 121.8 kg + top-up 7.4 kg. Seeding 45 directly
    would make the on-stage opt-out show 811/860 and break the script. `test_demo_seeder.py` pins both
    states; the HTTP smoke test reproduced both.
39. **Demo reset sets the clock to 08:30 before it re-seeds** (supersedes the order in #12). The scheduler
    tick runs in another thread; at the real time (after 09:00) it could issue the fresh lunch between the
    re-seed and the clock change. Order now: real time (to find today's IST date) -> 08:30 -> TRUNCATE ->
    re-seed. After a plain restart in demo mode the first tick issues today's lunch if the real time is
    past 09:00 (correct behaviour), so run the demo reset before a demo.
40. **A PLANNED meal follows its slot live.** The forecast is computed on every read from the opt-out rows
    + `extra_opt_outs` and the slot's *current* attendance ratio and buffer; the meal's
    `attendance_ratio`/`buffer_pct` columns are refreshed at create, edit and issue (the snapshot). Service
    times are copied from the slot at create and do not move later; the cutoff uses the slot's current
    `optout_cutoff_min`.
41. **Issue freezes everything:** P50/P90, `rule_p50`/`rule_p90` (the rule's numbers at issue, also for a
    MANUAL meal, so the comparison uses the final opt-outs), `opted_out_count`, ratio, buffer, `issued_at`,
    and each dish's `line_g`/`reserve_g` (with the kitchen's side-dish basis). An issued card's basis is
    read back from its frozen `line_g` (`cook_card.basis_used`), so a later change of the kitchen setting
    never changes it; top-up and raw kg are recomputed from the frozen numbers and the g/diner copied onto
    `meal_dish`. The reserve vessel's `planned_g` is set when the vessel is lidded (Phase 3), from the
    frozen `reserve_g`.
42. **Opt-outs close at the cutoff or when the card is issued, whichever comes first** (409
    `OPTOUT_CLOSED`, also for Undo): after issue the numbers are frozen, so accepting more would mislead
    the student. Open slot-dates are today and tomorrow (IST); a later date answers 409
    `OPTOUT_NOT_OPEN_YET`, a past one `OPTOUT_CLOSED`. Opting out again, or undoing twice, answers 200 with
    `changed: false`. Hostel IDs are trimmed and upper-cased, then checked against `APP_HOSTEL_ID_PATTERN`
    (400 `INVALID_HOSTEL_ID`); an empty one is a plain 400 `VALIDATION_FAILED`. An unknown kitchen code or
    a slot the kitchen does not serve is 404.
43. **Rate limit:** 30 opt-out + undo POSTs per client IP per 60 s (`APP_OPTOUT_RATE_LIMIT`,
    `APP_OPTOUT_RATE_WINDOW_S`; invalid tries count too), in memory (one worker, plan 2.2), timed with the
    app clock; hits outside [now - window, now] are forgotten, so a demo clock jump never locks a phone
    out. Generous because a hostel Wi-Fi shares one public IP. Over the limit: 429 `TOO_MANY_REQUESTS` with
    `Retry-After`. `ApiError` got an optional `headers` argument for this.
44. **Error codes added** (problem+json): 409 `ONE_RESERVE_DISH`, 409 `RESERVE_MUST_BE_VEG`, 400
    `DISH_ALREADY_ON_MENU`, 409 `DISH_INACTIVE`, 409 `MEAL_DATE_PAST` (meals are planned for today or
    later), 409 `MEAL_EXISTS`, 409 `MEAL_NOT_PLANNED` (edit/override/issue after issue), 400
    `OVERRIDE_NEEDS_REASON`, 400 `P90_BELOW_P50`, 409 `MEAL_NOT_IN_SERVICE` (door tally before issue), 409
    `COUNT_BELOW_ZERO`, 409 `NOT_A_PARTNER` (standing partner without an active MoU), 409 `CONCURRENT_EDIT`
    when a PUT/override sends an old `version`. Another kitchen's meal, slot or dish is 404 `NOT_FOUND`.
    A create checks "meal exists" before the menu, so a duplicate with a bad menu answers `MEAL_EXISTS`.
45. **API shapes.** `GET /api/kitchen/slots` answers `{kitchen, slots, partners}` (the pages need the
    registered count, the side-dish basis and the NGOs that can be a partner; there is no other kitchen
    endpoint for them). `GET /api/kitchen/meals?date=` answers `{date, meals, serverNow}` (default date:
    today on the server clock). Every meal command answers the full `MealView`; create answers 201;
    `registeredCount` is optional (default: the kitchen's registered diners). The meal view has the
    forecast, the cook card, the T-90 columns and `serverNow`; the reserve batch with SafeClock and the
    offer timeline join it in Phases 3-4. `GET .../open-meals` also carries `sampleData`, because the
    student page has no login and cannot call `/api/me`.
46. **Override (MANUAL)** is not capped at the eligible count (an event can bring guests). The plan has no
    "back to the rule" endpoint, so a manager who changes their mind overrides again with the rule numbers
    shown next to the manual ones.
47. **Door tally** works while ISSUED or IN_SERVICE, as one conditional UPDATE (`live_count + delta`,
    never below 0, version + 1), so two phones tapping +1 together both count.
48. **Scheduler steps 1-2** are wired. `auto_issue` re-checks PLANNED and the cutoff and relies on the
    meal's version column if the manager clicks at the same moment; `start_service` is one conditional
    UPDATE. `loop_tick` now also catches an error in a step's `find_due` (logged), so one broken step
    never stops the others. A meal planned after its start time is issued and started in the same tick.
49. **New service file `services/kitchen_setup.py`** (slots and dishes), next to the router of the same
    name; section 9 lists no service for kitchen setup.
50. **Pages.** One JS file per page (plus api/ui/i18n). `plan.js` refreshes every 15 s while the tab is
    visible and no form is open; the cook card on the plan page is a stacked list (a table did not fit
    360 px). The printed card shows English and Tamil together (`i18n.label(key, lang)`), marks a PLANNED
    card as DRAFT, and uses `print.css`. The student page remembers the last hostel ID and its opt-outs in
    this phone's localStorage only (to show Undo), wrapped in try/catch. `index.html` sends KITCHEN straight
    to `kitchen/plan.html`; ADMIN/NGO keep the welcome card. Toast text in dark mode uses a new
    `--on-status` colour (white on the light dark-mode green was hard to read).
51. **Checks run:** 340 tests pass (57 unit, 153 API, 130 integration; Phase 1 had 230). HTTP smoke test
    against the dev DB in demo mode (47 checks + 3 extra, all passed): reset to 08:30; open meals for MESS1
    (sampleData); seeded lunch 813/862; opt-out -> 812/861, duplicate harmless, undo -> 813/862, bad
    hostel ID 400, no CSRF 403; cook card 70.6 / 162.4 / 9.8 kg and sambhar 121.8 + 7.4 kg; tomorrow's
    lunch created and viewed (850/901); no reserve dish / two reserve dishes 409 `ONE_RESERVE_DISH`;
    override without a reason 400; issue -> frozen 812/861; opt-out after issue and after the 09:00 cutoff
    409; the live scheduler moved the lunch to IN_SERVICE after 12:00; tally 320 + 10; the four pages and
    their scripts 200; all 15 API calls in the page scripts exist in `/openapi.json` with that method;
    final demo reset (the dev DB is back to the seeded state). The pages were also viewed at 360 px in the
    desktop app's browser (student opt-out, confirm, undo, Tamil; plan, meal editor, cook card, setup)
    with no console errors. uvicorn was stopped; `annamsetu-db` is still running.

## Phase 2 adversarial verification, 26 Oct 2026

An independent re-check of the Phase 2 report against plan sections 3-7, 8.1, 8.2, 8.6 and 11.6 (nothing
taken on trust). Baseline before any change: 340 passed, 0 failed, as reported.

52. **The rules were re-derived, not re-read.** A scratch script re-implemented 8.1 and 8.2 with Python
    `Fraction`s (half up = floor(x + 1/2)) and compared them with `rules/forecast.py` and `rules/cook_card.py`:
    93,945 forecast cases (random registered / opted out / ratio / buffer, plus every eligible count 0-2000 x
    9 ratios x 5 buffers, so every x.5 boundary) and 20,000 random cook lines: **0 differences**. Hand-checked:
    registered 0 -> 0/0; opt-outs > registered -> 0/0; ratio 1.0 -> P50 = P90 = eligible (capped); buffer 0
    -> P90 = P50; 2.5 -> 3 and 812.5 -> 813 (not banker's rounding); raw kg only with raw g/diner; P50_TOPUP
    (line P50, top-up P90 - P50, raw for P50) vs P90 (line P90, no top-up); MANUAL P90 < P50 refused; a blank
    or spaces-only reason refused. 956 -> 813/862 (70.7 / 162.6 / 9.8 kg) and 955 -> 812/861 (70.6 / 162.4 /
    9.8 kg; sambhar 121.8 + 7.4 kg) as in 8.1/8.2/11.6. The two drafts stay as they were.
53. **Opt-out answers no longer carry `changed`** (supersedes that part of #42). Anyone can type any hostel
    ID, and opting out an ID that was already out changed nothing but answered `changed: false`: a trace-free
    way to find out which students skipped a meal (personal data, DPDP). Opt-out and undo now answer the same
    body (`kitchenCode, date, slot, optedOut, cutoffAt, serverNow`) whatever the earlier state. Repeats are
    still harmless. `optout.js` never read the field.
54. **Issue vs opt-out race closed** (it was listed as a known gap). Issue (the button and scheduler step 1),
    edit and override first lock the meal row (`SELECT ... FOR UPDATE`, `meals.lock_meal_row`); the opt-out
    and undo open check reads the meal `FOR SHARE` and keeps that lock until it commits. So an opt-out being
    saved while the card is issued is counted in the frozen numbers (the issue waits for it), and one that
    arrives during an issue waits and then gets 409 `OPTOUT_CLOSED`. A click on Issue at the same moment as
    the scheduler now answers a clean 409 `MEAL_NOT_PLANNED` (re-checked under the lock) instead of
    `CONCURRENT_EDIT`. `tests/integration/test_issue_optout_race.py` holds one side half way and runs the
    other in a thread; with either lock removed the tests fail (checked).
55. **The reserve dish stays veg after planning.** A meal copies its menu, and the cook card reads veg/non-veg
    from the dish, so turning a planned meal's reserve dish non-veg in setup slipped a non-veg reserve past
    the menu check (plan 8.2). `PUT /api/kitchen/dishes/{id}` now answers 409 `RESERVE_MUST_BE_VEG` while the
    dish is the reserve dish of a meal that is not CLOSED; side dishes, and dishes of closed meals, may change.
56. **setup.js**: tapping a tab or the language button before the data had loaded threw a TypeError
    (`state.setup` was still null); `render()` now waits for the data. The other page scripts were read for
    undefined names and element ids; a new API test checks that every `$('#id')` in a page script (and the
    tab/panel ids built at runtime) exists in its page.
57. **Tests:** 350 pass (57 unit, 158 API, 135 integration; was 340). New: the three race tests, the opt-out
    answer is identical for a known and an unknown hostel ID (and the OpenAPI shape has no state field), the
    veg guard on dishes, and the page id check.
58. **HTTP smoke test** (uvicorn in demo mode on the dev DB, fresh clients per role, 81 checks, all passed):
    pages, scripts and CSS served exactly as on disk, `print.css` linked for print; demo reset -> 08:30 and
    813/862 (70.7 / 162.6 / 9.8 kg as `fmtKg` in `ui.js` shows them, run in node); the student opt-out ->
    **P50 812 / P90 861, rice 70.6 kg raw, 162.4 kg serving line, 9.8 kg reserve vessel, sambhar 121.8 kg +
    7.4 kg top-up**; duplicate and "someone already out" give the same answer; no CSRF 403; bad hostel ID 400
    without echoing it; undo -> 813/862; 401/403 for anonymous/NGO/ADMIN on `/api/kitchen`; a wrong CSRF token
    is 403 on all 8 kitchen POST/PUT endpoints; override without reason / P90 < P50 400; issue freezes
    812/861, then opt-out and undo 409 `OPTOUT_CLOSED`, edit and override 409 `MEAL_NOT_PLANNED`, card
    unchanged; tally set/+10; one-reserve 409 for none and two; the reserve dish cannot turn non-veg; the
    **live scheduler** (demo clock moved to tomorrow 09:00:02, real 15 s tick) issued tomorrow's lunch with its
    opt-out counted (849/900) and started today's, then started tomorrow's at 12:00; the 31st opt-out POST from
    one IP got 429 with `Retry-After`; all 15 page API calls exist in `/openapi.json` with their method; the
    camelCase fields the pages read are all in the real responses; final demo reset back to the seeded state.
    The server log holds no hostel ID (it never goes in a URL) and no error. In the desktop app's browser
    pane at 360 px (no horizontal scroll, no script errors): student opt-out, confirm, Undo and Tamil; plan
    page, meal editor and a save (PUT); the bilingual cook card (DRAFT); setup slots/dishes in Tamil and the
    new veg guard message. uvicorn was stopped; `annamsetu-db` is still running.
