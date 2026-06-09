# Contributing

Thanks for helping improve InkWild.

Before making changes, read `CLAUDE.md` and the relevant module docs under `docs/`. They describe the backend async conventions, API contract, SSE event rules, model-routing layer, frontend design system, and the boundaries that should not be bypassed.

## Local Checks

```bash
cd backend && python -m pytest tests/ -v
cd frontend && npm run lint && npm run test
cd admin-frontend && npm run lint
```

## Repository Hygiene

Keep source files close to the system they belong to:

- Backend API routes live in `backend/api/`; reusable business logic goes in `backend/services/`; engine/runtime logic goes in `backend/engine/`; provider adapters go in `backend/llm/`.
- Backend schemas, SQLAlchemy models, migrations, seeds, and tests stay in `backend/schemas/`, `backend/models/`, `backend/migrations/`, `backend/seeds/`, and `backend/tests/`.
- Player-facing UI belongs in `frontend/`; admin-only UI belongs in `admin-frontend/`. Do not share visual systems between them unless a shared package is introduced deliberately.
- Durable docs belong in `docs/`. Private production notes, one-off operational SQL, screenshots, and local run outputs stay outside Git.
- Evaluation framework code may live under `backend/eval/`; generated evaluation runs belong under `backend/eval/runs/` and are ignored.

Do not commit:

- `.env` files or provider credentials
- Local SQLite databases
- Generated images or screenshots
- Production runbooks, production SQL patches, or private deployment details
- Evaluation run outputs under `backend/eval/runs/`
- AI-tool scratch directories such as `.claude/`, `.codex/`, `.impeccable/`, and `.superpowers/`

For frontend changes, keep the existing InkWild visual system and mobile-first constraints. For backend changes, keep the async FastAPI/SQLAlchemy architecture and route all LLM calls through the model router.
