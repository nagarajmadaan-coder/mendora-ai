# MENDORA API (backend) — Steps 10–12

A Python **FastAPI** backend with a **SQLite database**, **accounts and roles**, a **rule-based safety
assessment engine**, and **AI diagnosis**.

> ⚠️ **Limitations**
> - The **safety engine reads words**; it can't see the problem, and it can miss things or occasionally be over-cautious.
> - **AI diagnosis needs an API key.** Without one, diagnosis returns `ai_not_configured` — a result is never invented.
>   The safety engine needs **no** key.
> - AI results list **possible** causes, not confirmed diagnoses.

## Merged features (from the second project, rebuilt safely)

| Method | Path | Who | What |
| --- | --- | --- | --- |
| POST | `/api/bookings/{id}/estimate` | assigned technician | Labour + materials estimate (accepted, unpaid booking) |
| POST | `/api/bookings/{id}/estimate/approve` · `/decline` | customer | Payment is blocked until the estimate is approved |
| POST | `/api/bookings/{id}/review` | customer | 1–5 stars + comment, completed booking only, once |
| GET | `/api/technicians/{id}/reviews` | anyone | Reviews from completed bookings (customers not named) |
| POST / GET | `/api/repair-requests/{id}/photos` | owner / admin / accepted technician | Add (base64 JSON) / list photos |
| GET / DELETE | `/api/photos/{id}` | same / owner | Photo file / remove |
| GET | `/api/admin/stats` · `/api/admin/safety-escalations` | admin | Dashboard data |

Bookings now include `price_breakdown` (visit fee + estimate, platform fee `MENDORA_PLATFORM_COMMISSION_PERCENT`, default 10%)
and the payment summary includes `payout_status` (`held` → `released` on completion, `returned` on refund — sandbox).
Technician search results include `approx_distance_km` and `map_point` (approximate **area centres**, never addresses).
Back up the database and photos: `.venv\Scripts\python -m app.cli backup`.
New settings: `MENDORA_UPLOAD_DIR` (default `backend/uploads`), `MENDORA_PHOTO_MAX_MB` (10), `MENDORA_PHOTOS_PER_REQUEST` (3),
`MENDORA_PLATFORM_COMMISSION_PERCENT` (10). New tables (`reviews`, `request_photos`) and new columns are added automatically.

## What's new in Steps 10–12

- **Sandbox payments** (`app/payments/`): customers pay for an ACCEPTED booking in a clearly-labelled sandbox. There are no
  card fields at all; the tester picks the simulated outcome (success, declined, insufficient funds, provider error).
  - The charged amount is always the booking's **stored price**; the client's `expected_amount` must match or nothing is charged.
  - `idempotency_key` per attempt: re-sending it returns the same result. The database allows only **one succeeded payment
    per booking** (partial unique index), even with simultaneous requests.
  - A failed attempt never marks the booking paid. Cancelling a paid booking refunds it (simulated).
  - The provider is an interface (`providers.py`), so a real gateway can be added later. None is connected.
- **Production settings:** `MENDORA_ENVIRONMENT=production` requires a real JWT secret, turns off `/docs` (override with
  `MENDORA_API_DOCS=true`) and demo data (override with `MENDORA_DEMO_MODE=true`).
- **Docker:** `Dockerfile` here, plus `docker-compose.yml` in the project root — see `../docs/DOCKER.md`.

| Method | Path | Who | What |
| --- | --- | --- | --- |
| POST | `/api/bookings/{id}/payments` | booking's customer | Sandbox payment (201; failed outcome = status `failed`; same key again → 200 replay) |
| GET | `/api/bookings/{id}/payments` | booking's customer / admin | Attempts for one booking |
| GET | `/api/payments` | signed in | My payments (admins: all) |
| GET | `/api/payments/{id}` | owner / admin | One payment (others get 404) |

## What was added in Steps 7–9

- **Repair knowledge base** (`app/knowledge/`): 17 repair-guide entries in `data/entries.json`, written by the MENDORA team
  and marked **unverified** (not reviewed by licensed professionals). Keyword search (`retrieval.py`) can later be swapped
  for vector search. **Safety runs first**: high risk → nothing shown; medium → causes only, no steps; low → simple checks.
- **Repair-case memory**: technicians' confirmed causes are saved as **unverified** cases; only an admin can verify one,
  with a written basis. AI suggestions and customer guesses can never be verified. Only verified, anonymised cases are shown.
- **Technicians**: technicians edit their own profile and availability; **only admins verify**. Customers only see
  verified technicians (plus clearly-labelled **sample** technicians in demo mode). Matching is by trade and **service
  area**, never distance. No reviews or ratings are invented.
- **Bookings & consultations**: request a 2-hour visit or a 30-minute consultation (or the next free slot), see the listed
  rate first, then track it. **No payments, no live calls.** Double-booking is blocked by a database uniqueness rule.
- **In-app notifications** only. Nothing is emailed, texted or pushed.

### Sample (demo) technicians

```powershell
.venv\Scripts\python -m app.cli seed-demo
```
Creates 6 sample technicians (2 per trade), e.g. `sample.plumbing.1@demo.mendora.local`. You choose one password for all of
them, so you can sign in as a sample technician and accept bookings. They are labelled "Demo sample — not a real
technician" everywhere, can't be verified, and are hidden when demo mode is off (`MENDORA_ENVIRONMENT=production`).

### Booking rules

| Rule | Detail |
| --- | --- |
| Who | Only customers, for their **own** saved request, with a bookable technician of the **same trade** |
| When | On :00 or :30, within working hours (default 09:00–18:00 Asia/Kolkata), at least 60 min ahead, at most 60 days ahead |
| Where | Visits: the area must be one the technician covers. The address is shown to the technician **only after they accept** |
| Safety | The request's safety is re-checked. **High risk** needs `safety_acknowledged: true` ("I am safe; MENDORA isn't an emergency service"). A booking never lowers the risk |
| Conflicts | Same time with the same technician → `409 time_slot_unavailable`. Same request + type already open → `409 duplicate_booking` |
| Status | requested → accepted / rejected; requested or accepted → cancelled (before the start time); accepted → completed (after the start). Anything else → `409 invalid_status_transition` |

## Safety engine (Step 6)

Code: `app/safety/rules.py` (all rules, questions and advice as plain data) and `app/safety/engine.py`.

| Risk | When | What happens |
| --- | --- | --- |
| **high** | sparking, smoke/burning, exposed wires, shocks, overheating electrics; gas smell/hiss, CO alarm; sagging/collapsing structure, widening cracks; burst pipes/flooding; water near electrics; sewage backing up; heavy furniture tipping, overhead items coming loose, unsafe stairs/railings | Clear safety steps. **AI diagnosis and DIY are blocked** (`409 blocked_by_safety`), on every endpoint |
| **medium** | uncertain signs (buzzing, tripping breaker, warm socket, cracks, ceiling leaks, water heater faults, odd water, unstable furniture, broken glass, gas appliances), alarming/uncertain wording, and **any electrical job that isn't clearly simple** | No DIY. Yes/no/not-sure questions; professional recommended; AI may give a **professional-only** assessment (causes only) |
| **low** | nothing risky found | Normal AI diagnosis; anything unsafe the AI suggests is removed |

- Answers can **raise** a medium risk to high or **clear** it; a **high risk is never lowered** (it's stored as sticky).
- "No sparks" is ignored, but "not sure if it's sparking" counts. A "yes" to a follow-up question about danger counts.
- The safety result is stored on each request (`risk_level`, `safety_assessment`) and re-checked on the server
  before every diagnosis. The client can't send its own risk level.
- If the AI flags danger, the request is escalated to high and no AI text is kept.

Older databases are upgraded automatically at startup (missing safety columns are added; nothing is deleted).

## 1. Setup (once)

Use **Python 3.10 – 3.13** (3.13 recommended). Very new versions such as 3.15 may not have ready-made
Windows downloads for some libraries yet, and installation then fails with a
"Microsoft Visual C++ 14.0 or greater is required" error. Run these from the `backend` folder.

**Windows (PowerShell)**
```powershell
python3.13 -m venv .venv            # or: py -V:3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

**macOS / Linux**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## 2. Configure (`backend/.env`)

Copy `.env.example` to `.env` (same folder) and fill in your own values. **Never commit `.env`.**

**Windows:** `Copy-Item .env.example .env` then `notepad .env`

At minimum set:

| Setting | Why |
| --- | --- |
| `MENDORA_JWT_SECRET` | Signs login tokens. Without it, everyone is signed out whenever the server restarts. Generate one: `.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ANTHROPIC_API_KEY` | Enables AI diagnosis (default provider: Anthropic, model `claude-sonnet-5-5`). Get a key at https://console.anthropic.com |

Placeholder values copied unchanged from `.env.example` are **ignored on purpose** (treated as "not set").

**Nebius Token Factory:** set `MENDORA_AI_PROVIDER=nebius` and `NEBIUS_API_KEY=…` (optionally `MENDORA_AI_MODEL`, default
`openai/gpt-oss-120b` — any Token Factory model tagged "JSON mode" works). Then run
`.venv\Scripts\python -m app.cli check-ai`: it sends ONE harmless sample problem through the real diagnosis code and prints
`Result: WORKING` or the exact reason it failed. The key is never printed.

**AI web research (Tavily, optional):** set `TAVILY_API_KEY=…`. On a saved request, **Search the web with AI** shows Tavily's
AI summary of web pages plus the source links (`POST /api/repair-requests/{id}/web-research`). It is separate from — and not —
the AI diagnosis. Safety still comes first: high risk → not searched; medium risk → links only; low risk → summary and snippets,
screened sentence by sentence. Test with `.venv\Scripts\python -m app.cli check-web-research`.

**Switching AI provider:** set `MENDORA_AI_PROVIDER=openai`, `OPENAI_API_KEY=…` and `MENDORA_AI_MODEL=<model name>`.
For another OpenAI-compatible service, also set `MENDORA_AI_BASE_URL`. `MENDORA_AI_PROVIDER=none` turns AI off.
`GET /api/health` shows whether AI is configured (it can't prove the key is valid — only a real diagnosis can).

## 3. Database

- SQLite file `backend/mendora.db`, **created automatically** the first time the server starts (tables included).
- Data **survives restarts**.
- **Reset everything** (prototype only): stop the server and delete `mendora.db` (and any `mendora.db-wal` / `mendora.db-shm`).
- **Migrations:** missing tables are created at startup, and missing columns are added. Steps 7–9 only **add new tables**
  (`repair_cases`, `technician_profiles`, `bookings`, `booking_slots`, `notifications`; Step 10 adds `payments`), so an existing `mendora.db`
  keeps working — no command is needed. For bigger changes later, add [Alembic](https://alembic.sqlalchemy.org).
- Use another database by setting `MENDORA_DATABASE_URL` (any SQLAlchemy URL).

## 4. Create the first admin (there is no public admin sign-up)

```powershell
.venv\Scripts\python -m app.cli create-admin --email admin@example.com --name "Site Admin"
```
You'll be asked for the password twice (hidden while typing). The admin can then create technician accounts
with `POST /api/admin/users`.

## 5. Start the server

**Windows:** `.venv\Scripts\python -m uvicorn app.main:app --port 8000`
**macOS / Linux:** `.venv/bin/python -m uvicorn app.main:app --port 8000`

(Adding `--reload` restarts on code changes, but on Windows it can leave a hidden process holding port 8000.)

- API: http://localhost:8000 — interactive docs: **http://localhost:8000/docs**
- In /docs: register or log in, copy `access_token`, click **Authorize**, paste it.

## 6. Run the automated tests

**Windows:** `.venv\Scripts\python -m pytest -v` · **macOS / Linux:** `.venv/bin/python -m pytest -v`

Tests use a temporary database and a **simulated** AI provider — they never call a real AI API or touch `mendora.db`.

## Endpoints

| Method | Path | Who | What |
| --- | --- | --- | --- |
| GET | `/api/health` | anyone | Status, storage, whether AI is configured |
| GET | `/api/trades` | anyone | Plumbing / Electrical / Carpentry |
| POST | `/api/safety/assess` | anyone | Safety check only — nothing saved, no AI |
| POST | `/api/repair-requests/{id}/safety-answers` | owner / admin | Answer the request's safety questions |
| POST | `/api/auth/register` | anyone | Create a **customer** account (role can't be chosen) → token |
| POST | `/api/auth/login` | anyone | Email + password → token (5 failures → 15-minute lockout) |
| GET | `/api/auth/me` | signed in | Current user |
| POST | `/api/repair-requests` | anyone | Save a request (private to you if signed in) |
| GET | `/api/repair-requests` | customer / admin | Your history (admins: all) |
| GET | `/api/repair-requests/{id}` | owner / admin | One request (others get 404) |
| POST | `/api/repair-requests/{id}/diagnosis` | owner / admin | AI diagnosis if safety allows (409 when high risk; 20 per user per hour) |
| GET | `/api/repair-requests/{id}/guidance` | owner / admin | Matching repair guides, after the safety check |
| GET | `/api/knowledge/entries` | anyone | Browse guide entries (no steps) |
| GET | `/api/knowledge/entries/{id}` | anyone | One entry (no steps) |
| POST | `/api/knowledge/search` | anyone | Safety check + matching guides for a description (nothing saved) |
| GET | `/api/technicians` | anyone | Search by `trade`, `area`, `available`, `consultation` — with match reasons |
| GET | `/api/technicians/{id}` | anyone | Public profile (no contact details) |
| GET | `/api/technicians/{id}/availability?date=YYYY-MM-DD&booking_type=…` | anyone | Free start times that day |
| GET | `/api/technician/overview` | technician / admin | Profile status and open assigned bookings |
| GET / PUT | `/api/technician/profile` | technician | My profile (can't set verification, ratings or sample flag) |
| POST | `/api/technician/profile/submit-verification` | technician | Ask an admin to verify me |
| PATCH | `/api/technician/availability` | technician | available / busy / unavailable |
| POST | `/api/bookings/quote` | customer | Preview time, price and safety notes — nothing saved |
| POST | `/api/bookings` | customer | Request a visit or consultation (`next_available` for consultations) |
| GET | `/api/bookings` | signed in | Customers: mine · technicians: assigned to me · admins: all (`?status=`) |
| GET | `/api/bookings/{id}` | involved people / admin | One booking, with `allowed_actions` (others get 404) |
| POST | `/api/bookings/{id}/accept` · `/reject` | assigned technician / admin | Respond to a request (verified technicians only, or samples) |
| POST | `/api/bookings/{id}/cancel` | customer / technician / admin | Before the start time |
| POST | `/api/bookings/{id}/complete` | assigned technician / admin | After the start; optional confirmed cause → unverified repair case |
| GET | `/api/notifications` | signed in | My in-app notifications |
| POST | `/api/notifications/{id}/read` · `/read-all` | signed in | Mark read |
| GET | `/api/admin/technicians?status=` | admin | All technician profiles |
| POST | `/api/admin/technicians/{id}/verification` | admin | Verify or reject, with a note of what was checked |
| GET / POST | `/api/admin/cases` | admin | Repair-case memory: list / add |
| POST | `/api/admin/cases/{id}/verify` · `/reject` | admin | Verify (needs a written basis and a technician-confirmed cause) or reject |
| GET / POST | `/api/admin/users` | admin | List users / create technician or admin |
| PATCH | `/api/admin/users/{id}` | admin | Enable / disable an account |
| GET | `/api/admin/repair-requests` | admin | All requests |

All errors look like: `{"error": {"code": "…", "message": "…", "details": [{"field": "…", "message": "…"}]}}`

### Examples

**Register** `POST /api/auth/register`
```json
{ "email": "asha@example.com", "password": "a-long-passphrase", "full_name": "Asha Kumar" }
```
→ `201`
```json
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 3600,
  "user": { "id": "8c0a…", "email": "asha@example.com", "full_name": "Asha Kumar", "role": "customer", "is_active": true, "created_at": "2026-10-25T10:00:00Z" } }
```
Errors: `409 email_taken`, `422 validation_error` (bad email, password under 8 characters, or a `role` field).

**Login** `POST /api/auth/login` with `{ "email": "...", "password": "..." }` → same shape as above.
Errors: `401 invalid_credentials` (same message for unknown email and wrong password), `403 account_disabled`, `429 too_many_attempts`.

**Safety check** `POST /api/safety/assess` (no sign-in)
```json
{ "trade_id": "electrical", "description": "Sparks come out of the kitchen socket when I plug in the kettle." }
```
→ `200`
```json
{ "risk_level": "high", "allow_diy": false, "requires_professional": true, "ai_diagnosis": "blocked",
  "matched_hazards": [ { "id": "electrical_sparking", "category": "electrical", "label": "Sparking or arcing", "risk": "high", "matched_text": "Sparks" } ],
  "recommended_action": "Keep away from it and don't touch it. …", "safety_message": "Sparks, smoke, burning smells … ",
  "emergency": true, "emergency_steps": [ "Don't touch the socket, switch, appliance or cable.", "…" ],
  "clarifying_questions": [], "professional": "a qualified electrician", "rules_version": "2026-10-27.1", "…": "…" }
```
A medium result includes questions; send answers back as
`"clarifying_answers": [ { "question_id": "crack_signs", "answer": "no" } ]` (answers: `yes`, `no`, `not_sure`).

**Create a request** `POST /api/repair-requests` with header `Authorization: Bearer <token>`
```json
{ "trade_id": "plumbing", "description": "The kitchen sink drains very slowly and gurgles. It started two days ago." }
```
→ `201` with `"safety": { … }` (as above), `"diagnosis_status": "not_started"` (or `"blocked_by_safety"`), `"diagnosis": null`.

**Diagnose** `POST /api/repair-requests/{id}/diagnosis` (body optional)
```json
{ "follow_up_answers": [ { "question": "Are other drains also slow?", "answer": "No, only the kitchen sink." } ] }
```
→ `200`, the request with:
```json
"diagnosis": {
  "source": "ai",
  "summary": "Your kitchen sink is draining slowly and gurgling.",
  "possible_causes": [ { "title": "Partial clog in the trap", "explanation": "Grease or food can build up in the U-bend." } ],
  "follow_up_questions": [ "Are other drains in the house also slow?" ],
  "recommended_next_step": "Check whether other sinks or the shower are also draining slowly.",
  "professional_recommended": false,
  "professional_reason": null,
  "urgent_safety_warning": null,
  "disclaimer": "AI-generated from your description only … possibilities, not a confirmed diagnosis …",
  "provider": "anthropic", "model": "claude-sonnet-5-5", "generated_at": "2026-10-25T10:01:00Z"
}
```
`safety_mode` is `"professional_only"` for medium risk (next step is always a professional) and
`safety_filter_applied` is `true` when MENDORA removed unsafe AI suggestions. High risk → `409 blocked_by_safety`
(the AI is never called). Errors (no diagnosis is saved or invented):

| Status | Code | Meaning |
| --- | --- | --- |
| 503 | `ai_not_configured` | No provider / model / API key |
| 503 | `ai_rate_limited` | Provider is busy (HTTP 429) |
| 504 | `ai_timeout` | Provider too slow (after one retry for temporary errors) |
| 502 | `ai_provider_error` | Provider error (e.g. invalid key) — details are logged on the server only |
| 502 | `ai_invalid_response` | The model's answer failed validation |
| 409 | `blocked_by_safety` | The safety check found high risk |
| 429 | `too_many_requests` | More than 20 diagnoses in an hour for this user |
| 403 | `sign_in_required` | Request was created without an account |

## What is sent to the AI provider

Only the **trade name**, the **problem description** and any **follow-up answers**, with email addresses and phone
numbers replaced by `[email removed]` / `[phone removed]`. Never names, account emails, user IDs, request IDs,
tokens or photos.

## Code layout

```
backend/app/
  main.py              App setup: database, CORS, error handlers, rate limiters, routes
  config.py            Settings from environment / .env (placeholders rejected)
  db.py                SQLAlchemy engine + sessions; creates tables
  models.py            Tables: users, repair_requests, repair_cases, technician_profiles, bookings, booking_slots, notifications, payments
  schemas.py           Request/response shapes + validation (+ schemas_knowledge / _technician / _booking.py)
  security.py          Argon2 password hashing, JWT tokens
  errors.py            One JSON error shape for everything
  cli.py               `create-admin` and `seed-demo` commands
  repositories/        Database queries (users, repair_requests)
  services/            trades, rate_limit, repair_requests (API response mapping)
  safety/              Safety engine (no AI): rules.py (data) + engine.py (assess)
  services/safety_workflow.py   Runs/stores the safety check for requests; sticky high risk
  ai/                  AI diagnosis — separate from the routes:
    service.py           safety gate → redaction → provider → validation → output screening
    providers.py         Anthropic (default), OpenAI-compatible
    prompts.py           System prompt + required JSON structure (+ safety context)
    privacy.py           Removes emails / phone numbers
    http.py, errors.py   Network helper (stdlib), error types
  knowledge/           Repair knowledge base: data/entries.json, store.py (validated loading),
                       retrieval.py (keyword search, swappable), service.py (safety-gated guidance)
  services/cases.py    Repair-case memory (verification rules)
  services/technicians.py  Profiles, visibility, verification, search with match reasons
  services/bookings.py Booking rules: times, slots (no double-booking), status changes, privacy, notifications
  payments/            Sandbox payments: providers.py (interface + SandboxProvider), service.py (rules)
  api/routes/          health, trades, safety, auth, repair_requests, knowledge, cases, technicians,
                       technician, bookings, notifications, admin
backend/tests/         373 tests (temporary DB, simulated AI, sandbox payments)
```
