# MENDORA AI — merged prototype (Steps 1–12 + features from the second project)

AI-powered home repair assistant for plumbing, electrical and carpentry problems.

- **Frontend** (this folder): React + TypeScript + Vite + Tailwind. Safety check before anything else
  (no sign-in needed), sign in / register, save requests, AI diagnosis when safety allows, private history,
  matching repair guides, technician search, booking requests, sandbox payments, in-app notifications, technician profile.
- **Backend** (`backend/` folder): Python FastAPI + SQLite + JWT login + AI provider integration.
  See **[backend/README.md](backend/README.md)** for setup, configuration (API key), the admin command and endpoints.

Demo / not built: payments are a **sandbox simulation** (no real money, no card details); no live audio/video calls,
no email/SMS, no reviews, no admin screens. AI diagnosis needs a provider (not configured yet — Nebius comes later).
Sample technicians are demo records, not real people.

- **Docker:** see **[docs/DOCKER.md](docs/DOCKER.md)** (`docker compose up --build -d` → http://localhost:8080).
- **What's connected to what:** [docs/INTEGRATION_CHECKLIST.md](docs/INTEGRATION_CHECKLIST.md).
Photos are saved with signed-in requests (location data removed), shown to a technician only after they accept, and never sent to the AI.

**Merged features** (see [docs/COMPARISON.md](docs/COMPARISON.md)): admin dashboard, reviews from completed bookings,
technician estimates with customer approval, platform-fee breakdown, sandbox escrow, photo attachments, map with
approximate area-centre distances, repair-guide browser, and a backup command.

## Running both (two terminals)

| Terminal | Folder | Command |
| --- | --- | --- |
| Backend | `mendora-ai/backend` | `.venv\Scripts\python -m uvicorn app.main:app --port 8000` |
| Frontend | `mendora-ai` | `npm run dev` → open http://localhost:5173 |

## Frontend ↔ backend configuration

The frontend reads the backend address from `VITE_API_BASE_URL` at build time: unset → `http://localhost:8000`;
empty → same website (used by Docker, where nginx forwards `/api`); or a full URL for a separately hosted API.
To change it, copy `.env.example` to `.env` and restart `npm run dev`.
The API client is `src/lib/api.ts`. **No API keys are ever in the frontend** — the AI key stays in `backend/.env`.

## Run the frontend

Requires Node.js 20.19+ (22 recommended). Run these inside this folder (the one with `package.json`):

```bash
npm install        # install dependencies (first time, or after getting a new version)
npm run dev        # start the dev server → open http://localhost:5173
npm run build      # type-check + production build into dist/
npm run preview    # serve the production build locally
npm run typecheck  # TypeScript check only
```

## Screens

| URL | Screen |
| --- | --- |
| `/` | Home: hero, services, how it works, resolutions, safety |
| `/diagnose` | Repair intake: trade, description, optional photos (with preview), Continue |
| `/diagnose?trade=plumbing` | Intake with a trade pre-selected (`plumbing`, `electrical`, `carpentry`) |
| `/resolutions` | Resolution options, each with an honest label for what works today |
| `/technicians` | Find a technician: trade, area, availability and consultation filters (`?trade=`, `?consultation=1`, `?request=`) |
| `/book?technician=…&type=…` | Choose request, date and free time (or next free slot), address; review price; confirm |
| `/bookings` | My bookings (customers) or assigned bookings (technicians) + in-app notifications |
| `/bookings/<id>` | One booking: details, status history, sandbox payment, accept / decline / cancel / complete |
| `/technician/profile` | Technician accounts: edit profile, availability, ask for verification |
| `/guides` | Browse repair guides (causes and warnings; no DIY steps without a safety check) |
| `/admin` | Admin dashboard: stats, technician and repair-case verification, high-risk reports |
| `/login`, `/register` | Sign in / create a customer account (`?next=` returns you where you were) |
| `/account` | My requests: private history + account details + sign out |
| `/requests/<id>` | One saved request: safety result, matching repair guides, AI assessment, find a technician |
| `/about` | About MENDORA & safety (`/about#never-diy`, `/about#emergency`) |
| anything else | Friendly "Page not found" screen |

## Project structure

```
index.html                     HTML shell; loads src/main.tsx
vite.config.ts                 Vite + React + Tailwind plugins
public/favicon.svg             Browser tab icon
src/
  main.tsx                     Entry point: wraps the app in the router + intake store
  App.tsx                      Page frame (navbar, main, footer); picks the screen by URL
  index.css                    Tailwind import + colour tokens (navy, teal, canvas)
  types.ts                     Shared TypeScript types
  data/content.ts              All wording + ROUTES (every screen's URL in one place)
  lib/api.ts                   Backend API client (adds the login token automatically)
  state/AuthContext.tsx        Who is signed in (token kept in localStorage — prototype trade-off)
  lib/router.tsx               Tiny router: navigate, replace, goBack, <Link>, section scrolling
  lib/validateIntake.ts        Form + photo validation rules
  state/IntakeContext.tsx      Remembers the current request (text, trade, photos) across screens
  pages/                       Home, Diagnose, Request, Account, Login, Register, Resolutions, About, NotFound
  components/                  Reusable UI (Button, Badge, BackButton, PageHeader, Section, cards, …)
  components/intake/           IntakeForm, PhotoUpload, PhotoThumbnail
  components/safety/           SafetyPanel (high / medium / low result, safety questions)
  components/diagnosis/        DiagnosisCard (AI result, professional-only badge, follow-up questions)
  components/knowledge/        KnowledgeGuidance (repair guides allowed by the safety check)
  pages/TechniciansPage.tsx    Technician search;  BookPage.tsx  booking form + review
  pages/BookingsPage.tsx       Booking list + notifications;  BookingDetailPage.tsx  one booking + actions
  pages/TechnicianProfilePage.tsx  Technician's own profile
```

## Not built yet

Real payment processing, hosting on a real server (see docs/DOCKER.md), configured AI provider, live calls,
email/SMS, reviews, admin screens.
