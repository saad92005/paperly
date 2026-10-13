# Paperly task runner. Works on Linux/macOS/CI and on Windows (GNU make + Git for Windows).
ifeq ($(OS),Windows_NT)
SHELL := C:/PROGRA~1/Git/bin/bash.exe
endif
.SHELLFLAGS := -ec

# Load the root .env so recipes can use DATABASE_URL etc.
-include .env
export

API := apps/api

.PHONY: setup dev dev-api dev-web db-migrate db-status db-reset test test-api test-web lint lint-api lint-web types e2e eval eval-smoke

setup:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example - fill in DATABASE_URL and BETTER_AUTH_SECRET")
	cd $(API) && uv sync
	pnpm install

dev:
	pnpm exec concurrently -k -n api,web -c blue,magenta "$(MAKE) dev-api" "$(MAKE) dev-web"

dev-api:
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

dev-web:
	pnpm --filter web dev

# Apply new migrations in db/migrations to the database in DATABASE_URL (Neon; see ADR-007).
db-migrate:
	cd $(API) && PYTHONPATH=. uv run python scripts/migrate.py

db-status:
	cd $(API) && PYTHONPATH=. uv run python scripts/migrate.py --status

db-reset:
	@echo "On Neon, reset with a fresh branch (Neon console -> Branches -> Reset from parent), then: make db-migrate"

test: test-api test-web

test-api:
	cd $(API) && uv run pytest -q

test-web:
	pnpm --filter web test

lint: lint-api lint-web

lint-api:
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run pyright

lint-web:
	pnpm --filter web lint
	pnpm --filter web typecheck

types:
	cd $(API) && PYTHONPATH=. uv run python scripts/dump_openapi.py ../../packages/api-types/openapi.json
	pnpm --filter @paperly/api-types generate

e2e:
	@echo "Playwright e2e suite arrives in Phase 3 (docs/10)."

eval eval-smoke:
	@echo "The eval harness arrives in Phase 2 (docs/07)."
