# InkWild

InkWild is an AI-powered interactive narrative engine: players act in natural language, and a world engine coordinates story state, NPC memory, scene direction, narration, events, endings, and long-running sessions.

The product has two complementary modes:

- **Script mode**: authored mysteries and endings, with clues, truth conditions, and narrative progression.
- **Free mode**: open-world play inside the same simulation and character engine.

It also includes a creator workshop for generating worlds and scripts, plus an admin console for model routing, user operations, content review, costs, credits, announcements, and audit logs.

## What Is Inside

InkWild is organized as a monorepo with three deployable apps:

```text
backend/          FastAPI backend, narrative engine, LLM routing, services, models, migrations
frontend/         Player-facing Next.js app
admin-frontend/   Separate Next.js admin console
docs/             Architecture, module docs, operations notes, design references
ops/              Operational scripts used by Docker Compose services
```

The backend is built around a multi-agent runtime:

- **Director** decides what the scene needs, which NPCs are involved, and how state should change.
- **NPC agents** respond with isolated memory, relationships, schedules, intentions, and voice style.
- **Narrator** turns structured scene output into streaming prose.
- **World simulator** advances time, events, environment changes, and NPC movement.
- **Memory and case board systems** preserve long-running context and player discoveries.
- **LLM router** binds text, image, moderation, compression, and workshop tasks to configurable provider slots.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Redis, structlog, SSE
- **Frontend**: Next.js 16, React 19, TypeScript, Zustand, TanStack Query, Tailwind CSS v4
- **Admin**: Next.js 16, React 19, TypeScript, TanStack Query, Recharts
- **AI providers**: OpenAI-compatible text providers, Claude, Gemini-compatible endpoints, Grok/xAI, image generation providers, Tavily search
- **Deployment**: Docker Compose

## Quick Start

The fastest local path is Docker Compose. This runs the whole stack in containers and does not expose Postgres or Redis on the host, so it can coexist with local database services:

```bash
make setup
# Edit backend/.env and add DEEPSEEK_API_KEY for AI-powered play/generation.
make dev-docker
```

The Makefile uses the Compose project name `inkwild` by default, so `make stop` and `make clean` only target this local InkWild stack. Use `COMPOSE_PROJECT=your-name make dev-docker` if you want an isolated second stack.

Default local URLs:

- Player app: `http://localhost:3000`
- Admin console: `http://localhost:3001`
- Backend API: `http://localhost:8000`

If those ports are already in use, override them:

```bash
FRONTEND_PORT=3100 ADMIN_PORT=3101 BACKEND_PORT=8100 make dev-docker
```

The frontend API URL follows `BACKEND_PORT` automatically in Docker dev mode.
The backend CORS allowlist also follows `FRONTEND_PORT` and `ADMIN_PORT`.

Without provider keys the services can start, but AI play, workshop generation, image generation, search, email delivery, and OAuth features are limited or disabled. Put private keys only in local env files:

- Backend secrets and provider keys: `backend/.env`
- Player app public/runtime config: `frontend/.env.local`
- Admin app public/runtime config: `admin-frontend/.env.local`

At minimum, set `DEEPSEEK_API_KEY` in `backend/.env` for text generation. Optional integrations include `TAVILY_API_KEY`, `GROK_API_KEY`, `GPTIMAGE_API_KEY`, `RESEND_API_KEY`, OAuth client secrets, and `OSS_*` if you switch image storage to OSS.

## Manual Development

Start PostgreSQL and Redis:

```bash
make dev-infra
```

Run the backend:

```bash
cd backend
cp .env.example .env  # skip if make setup already created it
pip install -e ".[dev]"
alembic upgrade head
uvicorn main:app --reload --port 8000
```

Run the player app:

```bash
cd frontend
npm install
npm run dev
```

Run the admin console:

```bash
cd admin-frontend
npm install
npm run dev
```

## Configuration

Use the example environment files as the starting point:

- `backend/.env.example`
- `frontend/.env.example`
- `admin-frontend/.env.example`

Most AI capabilities are provider-slot based. You can run the app with only the providers you configure, while unavailable providers remain inactive or fall back according to the model-management layer.

## Development

Common checks:

```bash
cd backend && python -m pytest tests/ -v
cd frontend && npm run lint && npm run test
cd admin-frontend && npm run lint
```

Project-specific conventions live in:

- `CLAUDE.md` / `AGENTS.md` for coding-agent and project rules
- `docs/ARCHITECTURE.md` for system architecture
- `docs/operations/quick-deploy.md` for local and production deployment shortcuts
- `docs/modules/README.md` for module-level documentation
- `frontend/AGENTS.md` for frontend implementation constraints

## Repository Hygiene

The repository should contain source code, reproducible configuration, seed data, migrations, and public-facing documentation.

It should not contain local databases, private production runbooks, provider keys, generated screenshots, one-off SQL patches, evaluation run outputs, or AI-tool scratch directories.

## License

The public license has not been finalized yet. The project is intended to remain commercially usable by the original owner, with open-source distribution terms to be decided before public release.
