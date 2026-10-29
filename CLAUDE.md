# CLAUDE.md — Spasht (spashtpaytm)

Read docs/BUILD_PLAN.md before any work. Build ONE phase at a time; stop after each phase and wait for "Go Phase N".

## Non-negotiables
- Never commit secrets (.env, backend/secrets/, keys, service-account JSON).
- The AI never invents numbers: all amounts, rates, fees and dates come from KFS facts in the DB; every LLM text passes number_guard.
- Only the backend creates receipts. receipts / consents / audit_log / teachback_attempts are append-only (DB triggers).
- Code decides journey transitions; the LLM only understands and phrases.
- Synthetic data only; mask identifiers. Never ask for OTP/PIN/password/ID numbers by voice.
- Paytm-style UI = layout and feel only. No official Paytm logo artwork or app icon, no third-party logos, visible "Concept demo" label, never deploy publicly, QR codes never encode upi:// URLs.
- Every voice action has a tap/type alternative. DEMO_MODE must always complete the golden path.

## Conventions
- Frontend: React + Vite + TS strict + Tailwind; server-driven journey UI from TurnResponse.
- Backend: FastAPI + SQLAlchemy 2 + Alembic + Postgres; all Sarvam calls through app/ai/sarvam_client.py.
- Ports: web 5173 (proxies /api), api 8000, postgres **5433** (host; 5432 inside the container), adminer 8080.
- Commands (make, or npm run with the same names on Windows): setup | dev | migrate | seed | keys | test | lint | eval | tts-cache | demo-reset | tunnel.
- Never put tokens or personal data in URLs. Never copy personal details from the docs/reference/ screenshots.
- End of phase: lint + tests + acceptance checklist + update docs/PROGRESS.md and docs/DECISIONS.md + commit "phase-N: ...", then STOP.

## Local environment notes (this machine)
- Python: the venv is pinned to **python3.12** (`PYTHON ?= python3.12` in the Makefile). The system default is 3.15, which lacks reliable wheels for psycopg/pydantic-core.
- `uv` is not installed; the Makefile auto-detects it and falls back to `python -m venv`.
- Docker Desktop must be running before `make db-up` / `make dev`.
- Postgres is published on host port **5433** because a native postgres already owns 5432. Override with `POSTGRES_HOST_PORT`.
