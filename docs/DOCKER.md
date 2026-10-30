# Running MENDORA with Docker

Two containers, started together by `docker-compose.yml`:

| Container | What it runs | Reachable at |
| --- | --- | --- |
| `frontend` | nginx serving the built React app; forwards `/api/…` to the backend | http://localhost:8080 |
| `backend` | FastAPI (uvicorn, no auto-reload), SQLite database on the `mendora-data` volume | only from the frontend container |

The browser only talks to one address (`http://localhost:8080`), so no CORS setup is needed for this layout.

> **Verification status:** these files were written and checked (`docker compose config` passes), and the same
> configuration was run *outside* Docker (same start command, production settings, separate data folder, the
> production frontend build behind a proxy that mirrors `nginx.conf`). **The images themselves have not been built
> yet**, because the environment used to prepare them couldn't download base images from Docker Hub. Please
> treat the first `docker compose up --build` on your machine as the real test.

## Requirements

[Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose v2 (Linux).

## 1. Configure (once)

From the `mendora-ai` folder (the one with `docker-compose.yml`):

```powershell
Copy-Item docker.env.example docker.env      # macOS/Linux: cp docker.env.example docker.env
notepad docker.env                           # set MENDORA_JWT_SECRET (see below)
```

Generate a secret with `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
The backend **refuses to start** in production while the secret is missing or still the placeholder.

| Variable | Required | Meaning |
| --- | --- | --- |
| `MENDORA_JWT_SECRET` | **yes** | Signs login tokens (32+ characters) |
| `MENDORA_ENVIRONMENT` | yes | `production` (turns off API docs and, by default, demo data) |
| `MENDORA_CORS_ORIGINS` | yes | The address people open, e.g. `http://localhost:8080` or `https://mendora.example.com` |
| `MENDORA_DEMO_MODE` | no | `true` shows the clearly-labelled sample technicians; `false` for a real deployment |
| `MENDORA_PAYMENT_PROVIDER` | no | `sandbox` (simulated, no real money) or `none` |
| `MENDORA_AI_PROVIDER` | no | `none` until a provider is set up and tested |
| `MENDORA_PORT` | no | Host port for the website (default `8080`); set in your shell or a `.env` next to the compose file |

`docker.env` is in `.gitignore`. Never commit it.

## 2. Build and start

```powershell
docker compose up --build -d
docker compose ps            # both should become "healthy"
```

Open http://localhost:8080. API health: http://localhost:8080/api/health

## 3. First-time data

```powershell
docker compose exec backend python -m app.cli create-admin --email admin@example.com --name "Site Admin"
docker compose exec backend python -m app.cli seed-demo      # optional: sample technicians (demo mode)
```

Both commands ask for passwords (hidden while typing).

## 4. Inspect

```powershell
docker compose logs -f backend      # backend logs (Ctrl+C to stop following)
docker compose logs -f frontend
docker compose ps                   # status and health
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
```

## 5. Stop / start / update

```powershell
docker compose stop                 # stop, keep everything
docker compose start                # start again
docker compose down                 # remove containers — the database volume is KEPT
docker compose up --build -d        # after changing code
docker compose down -v              # ⚠ also deletes the database volume (all data)
```

## 6. Back up the database

```powershell
docker compose exec backend python -c "import sqlite3; s=sqlite3.connect('/data/mendora.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker compose cp backend:/data/backup.db ./mendora-backup.db
```

## Hosting on a real server (still manual)

These steps are **not done** and need your decisions:

1. A server or container host (any machine that runs Docker Compose, or a container platform).
2. A domain name and **HTTPS** (e.g. a reverse proxy such as Caddy/Traefik, or the platform's TLS) in front of port 8080.
   Then set `MENDORA_CORS_ORIGINS=https://your-domain`.
3. Set `MENDORA_DEMO_MODE=false` unless you want sample technicians visible.
4. Regular database backups (see above). For many users, move from SQLite to PostgreSQL (`MENDORA_DATABASE_URL`)
   and add proper migrations (Alembic).
5. Real payments: replace the sandbox provider with a real gateway (server-side confirmation/webhooks) — not built.
6. AI diagnosis: configure the provider (e.g. Nebius Token Factory) via the `MENDORA_AI_*` variables and test it — not done.
7. If the frontend and API are on **different** domains, rebuild the frontend with `VITE_API_BASE_URL=https://api.your-domain`.
