# MENDORA — Integration checklist (Step 11)

Every screen, the backend endpoints it uses, and how the connection was verified.
"API test" = `backend/tests/…` (pytest, real FastAPI app, temporary database).
"Browser test" = Playwright against the real frontend and backend.

| Area | Screen (URL) | Endpoints | Status | Verified by |
| --- | --- | --- | --- | --- |
| Registration & login | `/register`, `/login` | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | Connected | API tests (`test_auth.py`), browser tests |
| Expired / invalid sign-in | any signed-in screen | any → `401` | **Fixed in Step 11**: user is signed out and the login screen explains why; a server outage no longer deletes the saved sign-in | API test (`test_integration.py`), browser test |
| Role-based access | `/account`, `/bookings`, `/technician/profile` | `require_roles(...)` on every protected route | Connected | API tests (`test_auth.py`, `test_integration.py::test_admin_only_operations_stay_protected`) |
| Repair intake | `/diagnose` | `POST /api/safety/assess`, `POST /api/repair-requests` | Connected | API + browser tests |
| Request history | `/account`, `/requests/<id>` | `GET /api/repair-requests`, `GET /api/repair-requests/{id}` | Connected | API + browser tests |
| Safety assessment | intake + request page | `POST /api/safety/assess`, `POST /api/repair-requests/{id}/safety-answers` | Connected; server is authoritative | `test_safety.py`, `test_integration.py` (bypass attempts) |
| AI diagnosis | `/requests/<id>` | `POST /api/repair-requests/{id}/diagnosis` | Connected. **No provider configured** → clear "isn't set up yet" message; nothing invented | `test_diagnosis.py`, `test_integration.py`, browser test |
| Repair knowledge | `/requests/<id>` (guides) | `GET /api/repair-requests/{id}/guidance`, `POST /api/knowledge/search`, `GET /api/knowledge/entries` | Connected; blocked for high risk | `test_knowledge.py`, `test_integration.py`, browser test |
| Technician discovery | `/technicians` | `GET /api/technicians` | Connected; covered-area suggestions; errors shown | `test_technicians.py`, `test_discovery.py`, browser test |
| Technician profile & availability | `/technician/profile` | `GET/PUT /api/technician/profile`, `PATCH /api/technician/availability`, `POST …/submit-verification` | Connected | `test_technicians.py`, browser test |
| Booking & consultation | `/book`, `/bookings`, `/bookings/<id>` | `GET /api/technicians/{id}/availability`, `POST /api/bookings/quote`, `POST /api/bookings`, `GET /api/bookings[/{id}]`, `POST …/accept\|reject\|cancel\|complete` | Connected | `test_bookings.py`, `test_integration.py`, browser tests |
| Sandbox payment | `/bookings/<id>` (Payment panel) | `POST /api/bookings/{id}/payments`, `GET /api/bookings/{id}/payments`, `GET /api/payments[/{id}]` | **New in Step 10** | `test_payments.py`, `test_integration.py`, browser test |
| Booking & payment status | `/bookings` list, booking page | `payment` field inside every booking | Connected | API + browser tests |
| Notifications | navbar badge, `/bookings` | `GET /api/notifications`, `POST …/read`, `…/read-all` | Connected (in-app only) | `test_bookings.py`, browser tests |
| Admin tools | `/docs` (no admin screens) | `/api/admin/*` | Protected; usable from `/docs` in development | API tests |

## API configuration

| Item | How |
| --- | --- |
| Frontend → backend address | `VITE_API_BASE_URL` (build time). Unset → `http://localhost:8000`. Empty → same website (Docker/nginx proxies `/api`). Full URL → separate API host |
| CORS | `MENDORA_CORS_ORIGINS` (comma-separated). Not needed when the frontend and API share one website (Docker setup) |
| Secrets | Backend only (`backend/.env` or container environment). The frontend build contains no keys (checked in Step 12) |
| Errors | Every backend error has the shape `{"error": {code, message, details}}`; screens show `message` |

## Honest limits (by design, not bugs)

- AI diagnosis: provider not configured (Nebius Token Factory comes after Step 12).
- Technicians: demo samples only, labelled everywhere; no reviews.
- Payments: sandbox simulation only — no real money, no card details, no real gateway.
- Notifications: in-app only (no email/SMS/push). Consultations: no live audio/video.
- Matching: by service-area text, not GPS distance.
