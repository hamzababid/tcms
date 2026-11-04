# Developer commands (docs/04 §2). GNU make 3.81 compatible.
SHELL := /bin/bash
COMPOSE := docker compose
-include .env
WEB_PORT ?= $(or $(TCMS_WEB_PORT),5173)

.PHONY: help env up down logs ps migrate seed test test-backend test-frontend e2e lint lint-backend \
        lint-frontend format api-client api-client-check schema-check ci

help: ## List commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-18s %s\n", $$1, $$2}'

env:
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")
	@grep -q '^TCMS_SECRET_KEY=.\+' .env || { \
	  sk=$$(openssl rand -base64 48 | tr -d '\n=+/'); ek=$$(openssl rand -base64 32); \
	  sed -i.bak -e "s|^TCMS_SECRET_KEY=.*|TCMS_SECRET_KEY=$$sk|" -e "s|^TCMS_ENCRYPTION_KEYS=.*|TCMS_ENCRYPTION_KEYS=k1:$$ek|" .env \
	  && rm -f .env.bak && echo "generated local TCMS_SECRET_KEY and TCMS_ENCRYPTION_KEYS in .env"; }

up: env ## Start the stack (db, minio, mailpit, migrate, api, worker, web)
	$(COMPOSE) up -d --build
	@echo "waiting for the API..."; for i in $$(seq 1 90); do \
	  status=$$($(COMPOSE) ps api --format '{{.Health}}' 2>/dev/null); \
	  [ "$$status" = "healthy" ] && break; sleep 2; done; \
	  [ "$$status" = "healthy" ] || ($(COMPOSE) logs --tail 50 migrate api; exit 1)
	@echo "web http://localhost:$(WEB_PORT) · api http://localhost:$(or $(TCMS_API_PORT),8000) · mail http://localhost:$(or $(TCMS_MAILPIT_PORT),8025)"

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: ## Follow logs
	$(COMPOSE) logs -f --tail 100

ps:
	$(COMPOSE) ps

migrate: env ## alembic upgrade head (as tcms_owner)
	$(COMPOSE) run --rm migrate

seed: env ## Load demo data (dev profile)
	$(COMPOSE) run --rm --no-deps api tcms seed --profile dev

test: test-backend test-frontend ## Backend pytest + frontend vitest

test-backend:
	cd backend && uv run pytest -n auto

test-frontend:
	cd frontend && pnpm test

e2e: ## Playwright against the running stack
	cd frontend && E2E_BASE_URL=http://localhost:$(WEB_PORT) pnpm e2e

lint: lint-backend lint-frontend ## ruff, mypy, import-linter, eslint, tsc

lint-backend:
	cd backend && uv run ruff check src tests migrations && uv run ruff format --check src tests migrations \
	  && uv run mypy && uv run lint-imports

lint-frontend:
	cd frontend && pnpm lint && pnpm typecheck && pnpm format:check

format: ## Apply formatters
	cd backend && uv run ruff format src tests migrations && uv run ruff check --fix src tests migrations
	cd frontend && pnpm format

api-client: ## Export OpenAPI and regenerate frontend/src/api/schema.d.ts
	cd backend && uv run tcms openapi --output openapi.json
	cd frontend && pnpm api-client

api-client-check: api-client ## Fail if the committed client is out of date (US-005)
	git diff --exit-code -- backend/openapi.json frontend/src/api/schema.d.ts \
	  || (echo "OpenAPI client drift: run 'make api-client' and commit the result" && exit 1)

schema-check: ## Migrated schema == docs/schema baseline, alembic check, 99_verify.sql as tcms_app
	cd backend && uv run pytest tests/integration/test_schema.py -q

ci: lint test api-client-check ## Local equivalent of the CI gates (without images/E2E)
