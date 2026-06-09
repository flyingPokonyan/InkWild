# Quick Deploy

This page is the shortest path from a fresh clone to a running InkWild stack.

## Local Docker

Prerequisites: Docker Desktop or Docker Engine with Compose v2.

```bash
make setup
# Optional but needed for AI text generation:
# edit backend/.env and set DEEPSEEK_API_KEY
make dev-docker
```

This mode exposes only the app ports (`3000`, `3001`, `8000`). Postgres and Redis stay on Docker's internal network to avoid conflicts with local services.
The Makefile uses Compose project name `inkwild` by default. Override it with `COMPOSE_PROJECT=...` when you intentionally want a separate stack.

Open:

- Player app: http://localhost:3000
- Admin console: http://localhost:3001
- Backend API: http://localhost:8000

If those ports are already in use:

```bash
FRONTEND_PORT=3100 ADMIN_PORT=3101 BACKEND_PORT=8100 make dev-docker
```

The frontend API URL follows `BACKEND_PORT` automatically in Docker dev mode.
The backend CORS allowlist also follows `FRONTEND_PORT` and `ADMIN_PORT`.

Useful commands:

```bash
make logs
make stop
make clean   # removes containers and local Docker volumes
```

## Manual Development

Run only infrastructure in Docker:

```bash
make setup
make dev-infra
```

This mode exposes Postgres on `localhost:5432` and Redis on `localhost:6379` for a backend process running directly on the host.

Run backend:

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn main:app --reload --port 8000
```

Run frontend:

```bash
cd frontend
npm install
npm run dev
```

Run admin console:

```bash
cd admin-frontend
npm install
npm run dev
```

## Environment Files

Never commit real values.

| App | Local file | Example file | Notes |
|---|---|---|---|
| Backend | `backend/.env` | `backend/.env.example` | Private provider keys, database URL, Redis URL, OSS, email, OAuth |
| Player app | `frontend/.env.local` | `frontend/.env.example` | Public API URL and optional public Sentry DSN |
| Admin app | `admin-frontend/.env.local` | `admin-frontend/.env.example` | Public API URL, main-site URL, dashboard flags |

Minimum useful backend key:

```dotenv
DEEPSEEK_API_KEY=...
```

Optional integrations:

- `TAVILY_API_KEY` for web research in workshop generation.
- `GROK_API_KEY` / `GPTIMAGE_API_KEY` for alternate text and image providers.
- `IMAGE_STORAGE_BACKEND=oss` plus `OSS_*` for object storage.
- `EMAIL_BACKEND=resend` plus `RESEND_API_KEY` for real email delivery.
- OAuth client IDs/secrets for Google or LinuxDo login.

## Production Compose

Create `backend/.env` on the server first. Then:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -p inkwild up -d --build
```

The production override binds ports to `127.0.0.1`; put nginx, Caddy, or a cloud load balancer in front for TLS and public routing.

If you change `NEXT_PUBLIC_*` values, rebuild the affected frontend image because Next.js inlines them at build time.
