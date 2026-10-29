# Spasht task runner.
# Every target has an identical `npm run <name>` alias in the root package.json,
# so Windows teammates without `make` use the same command names.

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help setup db-up db-down migrate seed keys dev dev-api dev-web test lint \
        format eval tts-cache demo-reset tunnel clean

# Pinned to 3.12: the system default (3.15) has no reliable wheels for
# psycopg/pydantic-core. Override with `make PYTHON=python3.11 setup`.
PYTHON      ?= python3.12
VENV        := backend/.venv
PY          := $(VENV)/bin/python
COMPOSE     := docker compose -f infra/docker-compose.yml

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- setup -----

setup: ## Install backend + frontend deps and create .env files
	@echo "==> backend env ($(PYTHON))"
	@if command -v uv >/dev/null 2>&1; then \
		echo "    using uv"; \
		uv venv --python $(PYTHON) $(VENV); \
		VIRTUAL_ENV=$(VENV) uv pip install -e "backend[dev]"; \
	else \
		echo "    uv not found, using venv"; \
		test -d $(VENV) || $(PYTHON) -m venv $(VENV); \
		$(PY) -m pip install -q --upgrade pip; \
		$(PY) -m pip install -e "backend[dev]"; \
	fi
	@echo "==> frontend deps"
	@cd frontend && npm install
	@echo "==> .env files (never committed)"
	@test -f backend/.env  || cp backend/.env.example  backend/.env  && echo "    backend/.env ready"
	@test -f frontend/.env || cp frontend/.env.example frontend/.env && echo "    frontend/.env ready"
	@echo "==> done. Next: make db-up && make migrate && make dev"

# -------------------------------------------------------------- database -----

db-up: ## Start Postgres + Adminer and wait for health
	@$(COMPOSE) up -d
	@echo "==> postgres on localhost:5433 · adminer on http://localhost:8080"

db-down: ## Stop the containers (data is kept in the named volume)
	@$(COMPOSE) down

migrate: ## Apply Alembic migrations
	@cd backend && .venv/bin/alembic upgrade head

seed: ## Load the synthetic demo data (phase 2)
	@echo "seed lands in phase 2"

keys: ## Generate Ed25519 signing + transcript keys (phase 5)
	@echo "keys lands in phase 5"

demo-reset: ## Dev only: wipe journey data and re-seed (phase 2)
	@echo "demo-reset lands in phase 2"

# ------------------------------------------------------------------- run -----

dev: ## Run Postgres + backend + frontend together
	@$(MAKE) db-up
	@npx --yes concurrently --kill-others --names "api,web" --prefix-colors "blue,magenta" \
		"$(MAKE) dev-api" "$(MAKE) dev-web"

dev-api: ## Run only the backend (reload)
	@cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web: ## Run only the frontend
	@cd frontend && npm run dev

# ---------------------------------------------------------------- checks -----

test: ## Run backend + frontend tests
	@echo "==> backend"
	@cd backend && .venv/bin/python -m pytest
	@echo "==> frontend"
	@cd frontend && npx vitest run

lint: ## Lint and typecheck everything
	@echo "==> ruff"
	@cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
	@echo "==> tsc + eslint + prettier"
	@cd frontend && npx tsc -b && npm run lint

format: ## Auto-fix formatting and lint issues
	@cd backend && .venv/bin/python -m ruff check --fix . && .venv/bin/python -m ruff format .
	@cd frontend && npm run lint:fix

eval: ## Run the LLM eval suite (phase 7)
	@echo "eval lands in phase 7"

tts-cache: ## Pre-generate TTS audio for every template line (phase 6)
	@echo "tts-cache lands in phase 6"

# ----------------------------------------------------------------- misc -----

tunnel: ## Expose the frontend over HTTPS for phone testing (phase 12)
	@echo "tunnel lands in phase 12"

clean: ## Remove build output and caches (keeps .env and the DB volume)
	@rm -rf frontend/dist frontend/node_modules/.vite backend/.pytest_cache backend/.ruff_cache
	@find backend -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "==> cleaned"
