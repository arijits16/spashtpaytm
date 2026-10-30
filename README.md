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

**Phases 0–12 complete.** Three clients on one backend:

- **`ios/`** — the native SwiftUI iPhone app: the Paytm-style home screen, the
  voice journey (record → Saaras → engine → Bulbul → speak), the KFS viewer,
  OTP, the receipt card and the rescue agent's incoming-call screen.
- **`backend/`** — FastAPI: the journey engine (a deterministic state machine),
  the trust layer (hash chain, Ed25519, Merkle anchors, AES-256-GCM
  transcripts), the Sarvam clients, the Number Guard, the rescue scheduler and
  KFS ingestion.
- **`frontend/`** — the laptop-only website: admin sign-in, the live compliance
  dashboard over SSE, receipt verification with the tamper demo, the ledger,
  the KFS library and the demo controls.

Phase 13 is the device-and-demo-day setup, which is a human checklist — see
[Demo day](#demo-day) below.

The full specification is [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md); progress
per phase is [`docs/PROGRESS.md`](docs/PROGRESS.md); design decisions and
deviations are [`docs/DECISIONS.md`](docs/DECISIONS.md); the security posture is
[`docs/SECURITY.md`](docs/SECURITY.md); the architecture, with diagrams, is
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); and the script for the five
minutes on stage is [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

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
| `make eval` | LLM eval suite |
| `make audit` | `pip-audit` + `npm audit` (§13.12) |
| `make env-check` | Compare each `.env` with its example (`ARGS=--fix` appends the missing keys) |
| `make tts-cache` | Pre-generate the TTS audio the golden path speaks |
| `make demo-reset` | Wipe journey data, reset the ledger and re-seed |
| `make golden-path` | Walk the whole journey over HTTP and print every step |
| `make contracts` | Regenerate `contracts/fixtures/*.json` from the backend |
| `make tunnel` | HTTPS tunnel, so the phone can reach the laptop |
| `make ios-gen` / `ios-build` / `ios-test` / `ios-run` | XcodeGen + build + test + launch |
| `make ios-config` | Write `ios/Config/Secrets.xcconfig` from the current tunnel |

## Running the demo

```bash
make db-up && make migrate && make seed   # once
make keys                                 # once: Ed25519 + transcript keys
make tts-cache                            # once per language change: pre-generates the spoken lines
make demo-reset                           # before every rehearsal and every run
make dev                                  # Postgres + FastAPI :8000 + Vite :5173
```

Then, on the laptop, open **http://localhost:5173/dashboard** and sign in as an
admin. On the phone, open Spasht from the Loans tile.

With no network at all, set `DEMO_MODE=true` in `backend/.env`: the journey runs
on templates and the pre-generated audio, and the golden path still completes
(§10.6).

To check the backend end to end without any UI:

```bash
make golden-path ARGS=--all      # all three languages, taps
make golden-path ARGS=--voice    # the utterances a customer would speak
```

## Demo day

The full checklist is in [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). The short
version:

0. `make env-check` — every `.env` compared with its example. A `.env` from an
   earlier phase is missing the keys later phases added, and the symptom is
   never "a key is missing" but a receipt QR pointing at localhost.
1. Put your ngrok static domain in `backend/.env` as `NGROK_DOMAIN` and
   `PUBLIC_BASE_URL=https://<that domain>`, then `make tunnel`, then
   **`make ios-config`** — it writes `API_BASE_URL` and `PUBLIC_BASE_URL` into
   `ios/Config/Secrets.xcconfig` with the `//` escaped as `/$()/` (an xcconfig
   treats `//` as a comment, so a pasted URL silently truncates to `https:`),
   warns if `PUBLIC_BASE_URL` disagrees, and regenerates the Xcode project.
2. `make ios-build CONFIG=Debug` and install on each team iPhone through Xcode
   (Personal Team signing, Developer Mode on, trust the developer). A free team
   signs for **7 days**, so reinstall the night before.
3. Mirror the iPhone to the laptop for the projector: QuickTime → File → New
   Movie Recording → choose the iPhone as the camera.
4. Phone volume up, Do Not Disturb on, hotspot ready as a backup network, the
   dashboard already open, `make demo-reset` run, and the backup video recorded.
5. **Afterwards:** stop the tunnel, and rotate `SARVAM_API_KEY` and
   `DEMO_AUTH_KEY`.

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
├── contracts/fixtures/    API examples every client must decode
├── backend/               FastAPI + SQLAlchemy 2 + Alembic
│   ├── app/{api,auth,journey,adapters,ai,trust,events,rescue,kfs,seed,db}
│   └── tests/
├── frontend/              React 19 + Vite + TS strict + Tailwind v4
│   └── src/{components,features,lib,pages,styles}
└── ios/                   SwiftUI, generated from project.yml by XcodeGen
    └── SpashtPaytm/{App,Core,Features}
```

## Secrets

Nothing secret is ever committed. `.env`, `backend/secrets/`, signing keys and any
Firebase service-account JSON are gitignored; only `.env.example` files are tracked.
`docs/reference/` (Paytm screenshots used for look-matching) is gitignored too.

Keys needed to run everything:

| Variable | Where | Needed for |
|---|---|---|
| `SARVAM_API_KEY` | `backend/.env` | Speech-to-text, text-to-speech, the LLM, KFS extraction. Without it the backend runs in demo mode on templates and cached audio. |
| `VITE_FIREBASE_*` | `frontend/.env` | Google sign-in on the website |
| `DASHBOARD_ADMIN_EMAILS` | `backend/.env` | Who may open `/dashboard` |
| `DEMO_AUTH_KEY` | `backend/.env`, `frontend/.env`, `ios/Config/Secrets.xcconfig` | The dev-only demo session |
| `TTS_CACHE_SECRET`, `OTP_PEPPER`, `TRANSCRIPT_KEY`, signing keys | `backend/.env`, `backend/secrets/` | Written by `make keys` |
| `GoogleService-Info.plist` | `ios/Config/` | Google sign-in on the phone (optional; demo sign-in works without it) |

**The Sarvam key lives only in the backend.** No client ever calls Sarvam.
See `docs/BUILD_PLAN.md` Appendix D.

## Troubleshooting

**`role "spasht" does not exist`** — another Postgres owns the port. Check with
`lsof -nP -iTCP:5433 -sTCP:LISTEN`; confirm `DATABASE_URL` points at 5433.

**`Cannot connect to the Docker daemon`** — start Docker Desktop and wait for the
whale icon to settle.

**`No virtualenv at …/.venv`** — run `make setup` (or `npm run setup`).

**Frontend builds but types fail** — run `npx tsc -b` inside `frontend/` for the
full error; the project uses TS strict plus `noUncheckedIndexedAccess`.

**The phone cannot reach the backend** — the tunnel URL changed, or the xcconfig
has a `//` in it (which starts a comment, so the URL silently truncates). Write
`https:/$()/your-domain.ngrok-free.app` and rebuild. `GET /api/health` from
Safari on the phone is the fastest check.

**The assistant is silent** — run `make tts-cache`. A missing cache entry is a
quiet turn by design (§10.2): the caption is always on screen.

**The app asks for the microphone and then does nothing** — Settings → Spasht →
Microphone. Every voice action has a typing alternative; the keyboard button is
beside the mic.

**`alembic` says the database is not up to date** — `make migrate`. After
pulling a new migration, `make demo-reset` re-seeds.
