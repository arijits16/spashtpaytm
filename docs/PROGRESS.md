# Spasht — build progress

One line per phase. Tick a box only when its acceptance criteria in
`docs/BUILD_PLAN.md` §15 actually pass.

**Hackathon minimum:** phases 0–8, 11, 12. Phases 9 and 10 are stretch.

| Phase | What | Status |
|---|---|---|
| 0 | Project folder, Docker Postgres, FastAPI health, Vite React shell | ✅ done — 2026-10-29 |
| 1 | Firebase Google login, token verification, `users` table, demo auth | ✅ done — 2026-10-30 |
| 2 | Schema, append-only triggers, seed data, loan math, sample KFS PDFs | ⬜ not started |
| 3 | Paytm-style home, profile drawer, concept guardrails, PWA | ⬜ not started |
| 4 | Deterministic Spasht journey, server-driven UI, consent lock | ⬜ not started |
| 5 | Hash-chained signed receipts, verify page, tamper demo, Merkle anchors | ⬜ not started |
| 6 | Sarvam Saaras STT + Bulbul TTS voice loop, cache, demo mode | ⬜ not started |
| 7 | Sarvam-105B understanding, KFS Q&A, grading, re-explain, Number Guard, evals | ⬜ not started |
| 8 | Live compliance dashboard with SSE, KPIs, ledger, receipts | ⬜ not started |
| 9 | Rescue agent (stretch) | ⬜ not started |
| 10 | KFS ingestion with Sarvam Document Intelligence (stretch) | ⬜ not started |
| 11 | Polish, failure handling, demo reset, docs | ⬜ not started |
| 12 | Tunnel, device fixes, demo-day checklist | ⬜ not started |

---

## Phase 0 — done (2026-10-29)

- [x] `make setup && make dev` (and `npm run setup && npm run dev`) start everything
- [x] `http://localhost:5173` shows **Backend: OK · DB: OK** inside the phone frame
- [x] `/dashboard` shows the empty desktop layout (navy sidebar, 1100px min width)
- [x] `make lint` passes — ruff + ruff-format + tsc + eslint (0 warnings) + prettier
- [x] `make test` passes — 17 backend, 6 frontend
- [x] `git status` shows no secrets and no reference screenshots tracked
- [x] No console errors in the browser
- [x] `npm audit`: 0 vulnerabilities (root and frontend)

**Not yet built, by design:** auth (phase 1), every real table (phase 2), the real
home screen (phase 3). `make seed`, `keys`, `eval`, `tts-cache`, `demo-reset` and
`tunnel` are declared and print the phase that fills them in.

### Known issues / carried forward
- `backend/requirements.lock` is a `pip freeze` snapshot for reproducibility; the
  authoritative pins live in `backend/pyproject.toml`.
- Postgres is on host port **5433**, not 5432 — see `DECISIONS.md` D-004.

---

## Phase 1 — done (2026-10-30)

- [x] Google login works on the laptop; `/api/me` returns name, email, photo,
      `preferredLanguage` and `isAdmin`
- [x] Refreshing the page keeps the user signed in; Logout works
- [x] Protected routes return 401 without a token; `/dashboard` refuses non-admins
      (403 from the backend guard, explanatory screen on the frontend)
- [x] Demo auth works with no internet (`X-Demo-User`, dev-only)
- [x] Auth tests use a mocked token verifier
- [x] `make lint` clean; `make test` 45 backend + 10 frontend
- [x] No console errors in the browser

**Built:** `users` table + migration `0002_users` (with a language CHECK
constraint), `auth/firebase.py` (two verification paths), `auth/demo.py`,
`auth/users.py` (upsert + allowlist), `deps.py` (`current_user` / `current_admin`),
`GET`/`PATCH /api/me`; frontend `lib/firebase.ts`, `lib/auth.tsx`,
`lib/authContext.ts`, `lib/env.ts`, `lib/guards.tsx`, `LoginPage`, signed-in home.

### Bugs found and fixed during the phase
- Demo sign-in while a real Google session was live left the real identity active
  behind a `Session: demo` badge (DECISIONS D-016).
- The OTP log-redaction rule was mangling UUIDs, so `user_id` / `journey_id` were
  untraceable in logs (DECISIONS D-020). Regression tests added.

### Known issues / carried forward
- No component tests for `AuthProvider` or the guards yet (DECISIONS D-021);
  `@testing-library/react` is deferred to phase 11.
- `DEMO_AUTH=true` / `VITE_DEMO_AUTH=true` are enabled in the local `.env` files
  so the offline fallback is always one tap away. `.env.example` keeps them
  `false`.
- Google sign-in is verified as far as the OAuth handler and a real session; the
  team should still run it on a phone in phase 12.
