# Paperly task runner. Works on Linux/macOS/CI and on Windows (GNU make + Git for Windows).
ifeq ($(OS),Windows_NT)
SHELL := C:/PROGRA~1/Git/bin/bash.exe
endif
.SHELLFLAGS := -ec

# Load the root .env so recipes can use DATABASE_URL etc.
-include .env
export

API := apps/api
# Supabase CLI wants a plain postgres URL; the API uses the asyncpg driver form.
PG_URL = $(subst postgresql+asyncpg://,postgresql://,$(DATABASE_URL))

.PHONY: setup dev dev-api dev-web db-migrate db-reset test test-api test-web lint lint-api lint-web types e2e eval eval-smoke

setup:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example - fill in the Supabase values")
	cd $(API) && uv sync
	pnpm install

dev:
	pnpm exec concurrently -k -n api,web -c blue,magenta "$(MAKE) dev-api" "$(MAKE) dev-web"

dev-api:
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

dev-web:
	pnpm --filter web dev

# Apply new migrations in supabase/migrations to the database in DATABASE_URL (cloud Supabase; see ADR-004).
db-migrate:
	@test -n "$(DATABASE_URL)" || (echo "DATABASE_URL is not set in .env" && exit 1)
	pnpm exec supabase db push --db-url "$(PG_URL)" --include-all

db-reset:
	@echo "db-reset needs the local Docker stack, which this setup does not use (ADR-004)."
	@echo "Use 'make db-migrate' for new migrations, or reset the cloud DB from the Supabase dashboard."

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
