# Spasht (स्पष्ट) — loans you actually understand

A voice-first loan-clarity co-pilot, built as a **concept demo** inside a
Paytm-style app shell for the **Paytm Build for India AI Hackathon** (Track 2 —
AI-Powered Financial Journeys). Team: **Finovators**.

> **This is not the live Paytm app.** It imitates Paytm's layout and feel only.
> No official Paytm logo artwork, no real partner logos, no real money, no real
> KYC. All data is synthetic. It is never deployed publicly.

Spasht turns a loan application into a short conversation in the customer's own
language: she speaks, her details are pre-filled with consent, offers are ranked
by **true cost (APR)** rather than headline rate, the Key Fact Statement is
explained in five lines, and **the "I agree" button stays locked until a 3-question
teach-back is passed**. The result is a **Spasht Receipt** — a hash-chained,
Ed25519-signed record of what was explained, in which language, and how she
answered, which anyone can verify and nobody can quietly edit.

---

## Status

**Phase 1 of 12 complete** — scaffold, Docker Postgres, FastAPI, React shell, and
Firebase Google sign-in with backend token verification. See
[`docs/PROGRESS.md`](docs/PROGRESS.md).

The full specification is [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md). Design
decisions and deviations are in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop | any recent | **must be running** before `db-up` / `dev` |
| Node | 20+ LTS | |
| Python | 3.11–3.13 | the venv pins **3.12** (see DECISIONS D-001) |
| `make` | optional | Windows users run the identical `npm run` scripts |
| `uv` | optional | auto-detected; falls back to `venv` |

## Quick start

```bash
make setup      # venv + npm install + .env files from .env.example
make db-up      # Postgres (host port 5433) + Adminer on :8080
make migrate    # alembic upgrade head
make dev        # Postgres + FastAPI :8000 + Vite :5173
```

On Windows, or without `make`, every target has an identical npm script:

```bash
npm run setup && npm run db-up && npm run migrate && npm run dev
```

Then open **http://localhost:5173**. You will be sent to `/login`; sign in with
Google, or tap **Continue as demo user** (needs no network). The signed-in home
shows your profile and `Backend: OK · DB: OK`. Admins also get **/dashboard**.

### Signing in

| Path | Needs | Notes |
|---|---|---|
| Continue with Google | `VITE_FIREBASE_*` in `frontend/.env`, internet | The real flow |
| Continue as demo user | `DEMO_AUTH=true` + `VITE_DEMO_AUTH=true` | Dev only, offline, signs in as persona `sunita` |

`/dashboard` additionally requires the signed-in email to be in
`DASHBOARD_ADMIN_EMAILS` (`backend/.env`, comma-separated).

### Commands

| Command | What it does |
|---|---|
| `make setup` | Install both dependency sets, create `.env` files |
| `make db-up` / `db-down` | Start / stop Postgres + Adminer |
| `make migrate` | Apply Alembic migrations |
| `make seed` | Load synthetic demo data _(phase 2)_ |
| `make keys` | Generate Ed25519 + transcript keys _(phase 5)_ |
| `make dev` | Run everything together |
| `make test` | pytest + vitest |
| `make lint` | ruff + ruff-format + tsc + eslint + prettier |
| `make format` | Auto-fix all of the above |
| `make eval` | LLM eval suite _(phase 7)_ |
| `make tts-cache` | Pre-generate TTS audio _(phase 6)_ |
| `make demo-reset` | Wipe journey data and re-seed _(phase 2)_ |
| `make tunnel` | HTTPS tunnel for phone testing _(phase 12)_ |

## Ports

| Port | Service |
|---|---|
| 5173 | Frontend (proxies `/api` → 8000) |
| 8000 | Backend API |
| 5433 | Postgres on the host — **not 5432**, see DECISIONS D-004 |
| 8080 | Adminer (server `db`, user/password/db all `spasht`) |

## Layout

```
spashtpaytm/
├── CLAUDE.md              rules for Claude Code
├── Makefile               task runner (npm scripts mirror it)
├── scripts/               cross-platform setup + venv runner
├── infra/                 docker-compose: postgres 16 + adminer
├── docs/                  BUILD_PLAN · PROGRESS · DECISIONS · ARCHITECTURE
├── backend/               FastAPI + SQLAlchemy 2 + Alembic
│   ├── app/{api,auth,journey,adapters,ai,trust,events,rescue,seed,db}
│   └── tests/
└── frontend/              React 19 + Vite + TS strict + Tailwind v4
    └── src/{components,features,lib,pages,styles}
```

## Secrets

Nothing secret is ever committed. `.env`, `backend/secrets/`, signing keys and any
Firebase service-account JSON are gitignored; only `.env.example` files are tracked.
`docs/reference/` (Paytm screenshots used for look-matching) is gitignored too.

Keys needed later: `SARVAM_API_KEY` (phase 6) and the Firebase web config
(phase 1). See `docs/BUILD_PLAN.md` Appendix D.

## Troubleshooting

**`role "spasht" does not exist`** — another Postgres owns the port. Check with
`lsof -nP -iTCP:5433 -sTCP:LISTEN`; confirm `DATABASE_URL` points at 5433.

**`Cannot connect to the Docker daemon`** — start Docker Desktop and wait for the
whale icon to settle.

**`No virtualenv at …/.venv`** — run `make setup` (or `npm run setup`).

**Frontend builds but types fail** — run `npx tsc -b` inside `frontend/` for the
full error; the project uses TS strict plus `noUncheckedIndexedAccess`.
