# Spasht task runner.
# Every target has an identical `npm run <name>` alias in the root package.json,
# so Windows teammates without `make` use the same command names. (The `ios-*`
# targets need macOS and Xcode; there is no Windows equivalent.)

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help setup db-up db-down migrate seed keys dev dev-api dev-web test lint audit \
        format eval tts-cache demo-reset tunnel clean sarvam-smoke secret-scan \
        contracts kfs-pdfs golden-path ios-gen ios-open ios-build ios-test ios-run ios-config ios-icon \
        test-backend test-web lint-backend lint-web

# Pinned to 3.12: the system default (3.15) has no reliable wheels for
# psycopg/pydantic-core. Override with `make PYTHON=python3.11 setup`.
PYTHON      ?= python3.12
VENV        := backend/.venv
PY          := $(VENV)/bin/python
COMPOSE     := docker compose -f infra/docker-compose.yml

# --- iOS ---
# Override any of these per invocation, e.g. `make ios-build CONFIG=Release`.
IOS_DIR     := ios
IOS_PROJECT := $(IOS_DIR)/SpashtPaytm.xcodeproj
IOS_SCHEME  ?= SpashtPaytm
CONFIG      ?= Debug
# Optional preferred device name. Left empty so `scripts/ios-sim.sh` picks the
# newest available iPhone: a given model only exists on some runtimes, so a
# hard-coded name breaks whenever Xcode updates or on a teammate's machine.
# Override with e.g. `make ios-build SIMULATOR='iPhone 17 Pro'`.
SIMULATOR   ?=
DERIVED     := $(IOS_DIR)/build
XCPRETTY    := $(shell command -v xcbeautify 2>/dev/null)

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- setup -----

setup: ## Install backend + website deps, create .env files, enable the git hook
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
	@echo "==> website deps"
	@cd frontend && npm install
	@echo "==> .env files (never committed)"
	@test -f backend/.env  || cp backend/.env.example  backend/.env  && echo "    backend/.env ready"
	@test -f frontend/.env || cp frontend/.env.example frontend/.env && echo "    frontend/.env ready"
	@echo "==> git pre-commit hook (secret scan)"
	@git config core.hooksPath .githooks && echo "    core.hooksPath = .githooks"
	@echo "==> done. Next: make keys && make db-up && make migrate && make dev"

# -------------------------------------------------------------- database -----

db-up: ## Start Postgres + Adminer and wait for health
	@$(COMPOSE) up -d
	@echo "==> postgres on localhost:5433 · adminer on http://localhost:8080"

db-down: ## Stop the containers (data is kept in the named volume)
	@$(COMPOSE) down

migrate: ## Apply Alembic migrations
	@cd backend && .venv/bin/alembic upgrade head

seed: ## Load the synthetic demo data (idempotent)
	@echo "==> seeding personas, offers, KFS PDFs and the question bank"
	@cd backend && .venv/bin/python -m app.seed.run

kfs-pdfs: ## Regenerate only the sample KFS PDFs
	@cd backend && .venv/bin/python scripts/generate_kfs_pdf.py

demo-reset: ## Dev only: wipe journey data, reset the ledger, re-seed
	@cd backend && .venv/bin/python scripts/demo_reset.py

# ------------------------------------------------------------- secrets -------

keys: ## Fill the empty secrets in backend/.env (never overwrites, never prints)
	@$(PY) backend/scripts/gen_keys.py

secret-scan: ## Scan tracked files for anything that looks like a secret
	@node scripts/secret-scan.mjs

audit: ## Supply-chain check (§13.12): pip-audit + npm audit
	@echo "==> pip-audit"
	@cd backend && .venv/bin/python -m pip_audit --progress-spinner off || true
	@echo "==> npm audit (website)"
	@cd frontend && npm audit || true
	@echo "    advisories we accept, and why, are in docs/SECURITY.md section 12"

# ------------------------------------------------------------------- run -----

dev: ## Run Postgres + backend + website together
	@$(MAKE) db-up
	@npx --yes concurrently --kill-others --names "api,web" --prefix-colors "blue,magenta" \
		"$(MAKE) dev-api" "$(MAKE) dev-web"

dev-api: ## Run only the backend (reload)
	@# Bound to 127.0.0.1, never 0.0.0.0 (build plan 13.4): the ngrok tunnel is
	@# the only route in from outside. Forwarded headers are trusted from the
	@# local ngrok agent only, so a caller cannot spoof its own IP.
	@# `--no-server-header` because uvicorn appends `Server: uvicorn` after the
	@# ASGI layer, so middleware cannot remove it (build plan 13.10: no server
	@# banner details).
	@cd backend && .venv/bin/uvicorn app.main:app --reload \
		--host 127.0.0.1 --port 8000 \
		--no-server-header \
		--proxy-headers --forwarded-allow-ips 127.0.0.1

dev-web: ## Run only the website
	@cd frontend && npm run dev

tunnel: ## Expose the backend over HTTPS for iPhone testing
	@scripts/tunnel.sh

# ---------------------------------------------------------------- checks -----

test: test-backend test-web ## Run backend + website tests

test-backend:
	@echo "==> backend"
	@cd backend && .venv/bin/python -m pytest

test-web:
	@echo "==> website"
	@cd frontend && npx vitest run

lint: lint-backend lint-web secret-scan ## Lint, typecheck and scan for secrets

lint-backend:
	@echo "==> ruff"
	@cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

lint-web:
	@echo "==> tsc + eslint + prettier"
	@cd frontend && npx tsc -b && npm run lint

format: ## Auto-fix formatting and lint issues
	@cd backend && .venv/bin/python -m ruff check --fix . && .venv/bin/python -m ruff format .
	@cd frontend && npm run lint:fix
	@command -v swift-format >/dev/null 2>&1 \
		&& swift-format format --in-place --recursive $(IOS_DIR)/SpashtPaytm $(IOS_DIR)/SpashtPaytmTests \
		|| echo "    swift-format not installed, skipping Swift"

golden-path: ## Walk the whole journey over HTTP and print each step
	@cd backend && .venv/bin/python scripts/play_golden_path.py $(ARGS)

contracts: ## Regenerate contracts/fixtures/*.json from the backend
	@echo "==> regenerating contract fixtures"
	@cd backend && SPASHT_WRITE_CONTRACTS=1 .venv/bin/python -m pytest tests/test_contracts.py -q
	@echo "    wrote contracts/fixtures/ - now update the iOS and website models if the shape changed"

sarvam-smoke: ## Check the Sarvam key and the TTS/STT/LLM endpoints
	@cd backend && .venv/bin/python scripts/sarvam_smoke.py

eval: ## Run the understanding + guard eval suite, writing docs/EVAL.md
	@cd backend && .venv/bin/python -m evals.run $(ARGS)

tts-cache: ## Pre-generate TTS audio for every template line
	@cd backend && .venv/bin/python scripts/tts_cache.py $(ARGS)

# ------------------------------------------------------------------- ios -----

ios-gen: ## Regenerate SpashtPaytm.xcodeproj from ios/project.yml
	@command -v xcodegen >/dev/null 2>&1 || { \
		echo "xcodegen is not installed. Run: brew install xcodegen"; exit 1; }
	@cd $(IOS_DIR) && xcodegen generate
	@echo "==> $(IOS_PROJECT) regenerated"

ios-config: ## Wire Secrets.xcconfig from backend/.env + GoogleService-Info.plist
	@$(IOS_DIR)/scripts/configure_secrets.sh

ios-icon: ## Redraw the app icon (navy square, white S)
	@python3 $(IOS_DIR)/scripts/make_app_icon.py

ios-open: ## Open the project in Xcode
	@test -d $(IOS_PROJECT) || $(MAKE) ios-gen
	@open $(IOS_PROJECT)

ios-build: ## Build the app (CONFIG=Debug|Release)
	@test -d $(IOS_PROJECT) || $(MAKE) ios-gen
	@echo "==> building $(IOS_SCHEME) ($(CONFIG)) for the Simulator"
	@set -o pipefail; UDID=$$(scripts/ios-sim.sh "$(SIMULATOR)") && xcodebuild build \
		-project $(IOS_PROJECT) \
		-scheme $(IOS_SCHEME) \
		-configuration $(CONFIG) \
		-destination "id=$$UDID" \
		-derivedDataPath $(DERIVED) \
		-quiet \
		CODE_SIGNING_ALLOWED=NO \
		| { [ -n "$(XCPRETTY)" ] && xcbeautify || cat; }

ios-test: ## Run the XCTest suite in the Simulator (CONFIG=Debug|Release)
	@test -d $(IOS_PROJECT) || $(MAKE) ios-gen
	@echo "==> testing $(IOS_SCHEME) ($(CONFIG))"
	@set -o pipefail; UDID=$$(scripts/ios-sim.sh "$(SIMULATOR)") && xcodebuild test \
		-project $(IOS_PROJECT) \
		-scheme $(IOS_SCHEME) \
		-configuration $(CONFIG) \
		-destination "id=$$UDID" \
		-derivedDataPath $(DERIVED) \
		-quiet \
		CODE_SIGNING_ALLOWED=NO \
		| { [ -n "$(XCPRETTY)" ] && xcbeautify || cat; }

ios-run: ## Build, boot the Simulator, install and launch the app
	@scripts/ios-run.sh "$(SIMULATOR)" "$(CONFIG)" "$(DERIVED)"

# ----------------------------------------------------------------- misc -----

clean: ## Remove build output and caches (keeps .env and the DB volume)
	@rm -rf frontend/dist frontend/node_modules/.vite backend/.pytest_cache backend/.ruff_cache
	@rm -rf $(DERIVED) $(IOS_DIR)/SpashtPaytmTests/Fixtures
	@find backend -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "==> cleaned"
