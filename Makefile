COMPOSE_PROJECT ?= inkwild
COMPOSE_DEV = docker compose -p $(COMPOSE_PROJECT) -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_INFRA = docker compose -p $(COMPOSE_PROJECT) -f docker-compose.yml -f docker-compose.infra.yml

.PHONY: setup dev-docker dev-infra stop logs test-backend test-frontend test-admin clean

setup:
	@test -f backend/.env || cp backend/.env.example backend/.env
	@test -f frontend/.env.local || cp frontend/.env.example frontend/.env.local
	@test -f admin-frontend/.env.local || cp admin-frontend/.env.example admin-frontend/.env.local
	@echo "Local env files are ready. Edit backend/.env and add provider keys for AI features."

dev-docker: setup
	$(COMPOSE_DEV) up -d --build backend frontend admin-frontend

dev-infra:
	$(COMPOSE_INFRA) up -d db redis

stop:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f

test-backend:
	cd backend && python -m pytest tests/ -v

test-frontend:
	cd frontend && npm run lint && npm run test

test-admin:
	cd admin-frontend && npm run lint

clean:
	$(COMPOSE_DEV) down -v
