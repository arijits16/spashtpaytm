# CLAUDE.md — Spasht (spashtpaytm)

Read docs/BUILD_PLAN.md (v2) before any work. Build ONE phase at a time; stop after each phase and wait for "Go Phase N".

## Layout
- backend/ FastAPI + Postgres (host port 5433) + Sarvam — shared brain
- frontend/ laptop website only: admin login, dashboard, receipt check + tamper demo
- ios/ native SwiftUI iPhone app (XcodeGen project.yml) — customer side
- contracts/fixtures/ — API examples every client must decode

## Non-negotiables
- Never commit or print secrets (.env, backend/secrets/, ios/Config/Secrets.xcconfig, GoogleService-Info.plist, keys).
- The Sarvam key lives only in the backend. Clients never call Sarvam.
- The AI never invents numbers: all figures come from KFS facts; every LLM text passes number_guard.
- Only the backend creates receipts; evidence tables are append-only.
- Server-driven journey: the app and website hold no business logic. Code decides transitions; the LLM only understands and phrases.
- Every route: auth, ownership (404 for others' data), validation, rate limit, standard error format.
- Demo auth only with DEMO_AUTH=true + APP_ENV=dev + correct X-Demo-Key; never in iOS Release builds.
- Synthetic data only. Never copy personal details from docs/reference/ screenshots.
- Paytm-style UI = layout and feel only. No official logo artwork or app icon, no third-party logos, keep "Concept demo" labels, install only on team devices, never deploy publicly, QR codes never encode upi:// URLs.
- Every voice action has a tap/type alternative. DEMO_MODE must always complete the golden path.
- Don't kill or restart the human's running dev servers; ask.

## Conventions and gotchas
- Postgres host port 5433 (D-004). Python 3.12 in backend/.venv. Tailwind v4 @theme tokens. TypeScript 6.0.3.
- Commands (make, or npm run with the same names): setup | db-up | dev | migrate | seed | keys | test | lint | secret-scan | contracts | eval | tts-cache | demo-reset | sarvam-smoke | tunnel | ios-gen | ios-open | ios-build | ios-test | ios-run | ios-config
- xcconfig URLs must be written https:/$()/host (// starts a comment).
- End of phase: lint + tests + ios-build + ios-test + Simulator screenshot check + acceptance checklist + update PROGRESS/DECISIONS/SECURITY + commit "phase-N: ...", then STOP.

## Local environment notes (this machine)
- Python: the venv is pinned to **python3.12** (`PYTHON ?= python3.12` in the Makefile). The
  system default is 3.15, which lacks reliable wheels for psycopg/pydantic-core (D-001).
- `uv` is not installed; the Makefile auto-detects it and falls back to `python -m venv` (D-002).
- Docker Desktop must be running before `make db-up` / `make dev`.
- Postgres is published on host port **5433** because a native postgres already owns 5432.
  Override with `POSTGRES_HOST_PORT`.
- Xcode 27 with iOS Simulator runtimes 18.6 / 26.5 / 27.0; XcodeGen installed via Homebrew.
- `ngrok` and `gitleaks` are **not** installed here. `make secret-scan` falls back to its own
  regex scanner (D-029); `make tunnel` tells you how to install ngrok.
