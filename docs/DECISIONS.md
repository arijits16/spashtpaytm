# Design decisions

Short entries, newest phase last. Record anything a future reader would otherwise
have to reverse-engineer — especially deviations from `BUILD_PLAN.md`.

---

## Phase 0

### D-001 — Backend Python pinned to 3.12, not the system default
The dev machine's default is Python 3.15, which has no reliable wheels for
`psycopg` and `pydantic-core`; installs fall back to source builds and break.
`pyproject.toml` declares `requires-python = ">=3.11,<3.14"` and the Makefile
defaults to `PYTHON ?= python3.12`. Override with `make PYTHON=python3.11 setup`.

### D-002 — `uv` is optional, `venv` is the fallback
The plan recommends `uv`. It is not installed here, and installing a global tool
is not ours to decide. `make setup` and `scripts/setup.mjs` both detect `uv` and
use it when present, otherwise `python -m venv`. Same result either way.

### D-003 — Tailwind v4, so the tokens live in CSS, not `tailwind.config.ts`
Current stable is Tailwind 4.3.3, which reads its theme from an `@theme` block in
CSS. There is therefore **no `tailwind.config.ts`** — §5.2's tokens are defined
once in `frontend/src/styles/index.css` and are usable both as Tailwind utilities
(`bg-card`) and as plain CSS variables (`var(--color-card)`). The plan anticipated
this exact change (§3, "Versions"). We also use the `@tailwindcss/vite` plugin,
which removes the need for `postcss.config.js` and `autoprefixer`.

### D-004 — Postgres is published on host port 5433
A native Postgres already owns `localhost:5432` on this machine and shadows the
container, producing a confusing `role "spasht" does not exist`. Rather than stop
a service the user is running, `infra/docker-compose.yml` publishes
`${POSTGRES_HOST_PORT:-5433}:5432`. The container still listens on 5432 internally,
so Adminer's `db:5432` is unchanged. To use 5432, set `POSTGRES_HOST_PORT=5432`
and update `DATABASE_URL`.

### D-005 — TypeScript pinned to 6.0.3, not the latest 7.0.2
`typescript-eslint@8.72.1` declares a peer range of `typescript >=4.8.4 <6.1.0`.
TypeScript 7 (the native port) would silently disable type-aware linting, and
type-aware rules are what keep the hand-written API boundary in §8.2 honest.
6.0.3 is the newest version inside that range. Revisit when typescript-eslint
ships TS 7 support.

### D-006 — `baseUrl` dropped from tsconfig
TS 6 deprecates `compilerOptions.baseUrl`. The `@/*` path mapping now resolves
relative to the tsconfig itself, and `vite.config.ts` carries a matching
`resolve.alias` (tsconfig paths alone do not affect Vite's bundling).

### D-007 — A custom `frame` breakpoint at 500px ~~(superseded by D-023)~~
§5.8 puts the phone bezel at **≥ 500px**, which is not any Tailwind default
(`sm` is 640px). `--breakpoint-frame: 500px` is declared in `@theme`, and
`PhoneFrame` uses `frame:` variants. Between 500 and 640px the app is framed,
exactly as the plan specifies.

> **Superseded in v2:** `PhoneFrame` no longer exists — the website is
> laptop-only and the customer UI is the native iOS app (D-022, D-023). The
> `--breakpoint-frame` token is unused but harmless and is left in `@theme`.

### D-008 — Synchronous SQLAlchemy engine
Journey transitions are short, request-scoped transactions. A sync engine with a
small pool is simpler to reason about and to test, and matches plan rule 15
("prefer simple and reliable over clever"). Sarvam calls are async and happen
outside the DB transaction, so they are not blocked by it.

### D-009 — `/api/health` always returns 200
Even when the DB is down. A 5xx would surface in the browser as a generic network
failure; returning 200 with `status: "degraded"` lets the UI say precisely what is
broken. The verdict lives in the body, not the status line.

### D-010 — PII redaction is a logging filter, not a call-site discipline
`app/logging.py` attaches `PiiRedactionFilter` to the root logger, so a careless
`logger.info(user_text)` anywhere in the codebase is still scrubbed. Rupee amounts
and percentages are deliberately **not** redacted — they are product facts we need
in logs to debug the Number Guard, and they are not personal data.

### D-011 — `eslint . --max-warnings 0`
Warnings that nobody fixes become noise that hides real problems. Lint is binary.

### D-012 — `concurrently` pinned to 9.2.5
9.2.1 pulls a `shell-quote` with two critical advisories. 9.2.5 is the lowest
version in the 9.x line that resolves them. Root and frontend both audit clean.

---

## Phase 1

### D-013 — Two Firebase verification paths, tried in order
`firebase_admin.auth.verify_id_token` first; on any failure, `google-auth`'s
`id_token.verify_firebase_token` with `audience=FIREBASE_PROJECT_ID`. The plan
(§13) allows the fallback for machines without ambient Google credentials, which
is the common hackathon-laptop case. Both check signature, issuer, audience and
expiry against Google's published keys, so the fallback is not weaker.

### D-014 — `is_admin` is recomputed on every request ~~(amended by D-037, D-038)~~
It is derived from `DASHBOARD_ADMIN_EMAILS` inside `upsert_user`, never stored as
a client-settable field. Removing an email from the allowlist revokes access on
the next request rather than at the next login, and a `PATCH /api/me` carrying
`isAdmin` is simply ignored. Both behaviours are tested.

> **Amended in v2:** the allowlist check now also requires `email_verified`
> (D-037), and an unknown field in `PATCH /api/me` is a 422 rather than ignored
> (D-038).

### D-015 — Demo uids are namespaced `demo:<persona>`
A demo user and a real Firebase account can therefore never collide on
`users.firebase_uid`, and demo rows are trivially identifiable for cleanup.

### D-016 — Demo sign-in signs out of Firebase first
The API client prefers a bearer token over `X-Demo-User` (mirroring the backend's
precedence in `app/deps.py`). Found in manual testing: tapping "Continue as demo
user" while a real Google session was live left the real identity active while
the UI showed a `Session: demo` badge. `signInAsDemoUser` now ends the Firebase
session before establishing the demo one, so the badge can never lie.

### D-017 — `AuthProvider` is split across three modules
`env.ts` (flags), `authContext.ts` (context + `useAuth`), `auth.tsx` (the
provider component only). React Fast Refresh only works when a module exports
components exclusively, and a broken Fast Refresh during a live demo means full
reloads and lost state.

### D-018 — The initial auth status is computed synchronously
`initialStatus()` runs in the `useState` initialiser rather than an effect, and
`fetchMe()` returns a result instead of setting state. This avoids the cascading
re-render that `react-hooks/set-state-in-effect` flags, and removes the flash of
the login screen for an already-signed-in user.

### D-019 — `preferred_language` has a DB CHECK constraint
The API validates it via a Pydantic `Literal` (clean 422s), and the `users` table
additionally constrains it to `mr-IN | hi-IN | en-IN`. Defence in depth: a buggy
endpoint must not be able to persist an unsupported locale that the journey
templates cannot render.

### D-020 — The OTP redaction pattern excludes hyphenated tokens
Found when a log line read `user_id: 9a[OTP]-9636-...`: the old `\d{6}` rule was
firing inside UUIDs, making `user_id` and `journey_id` untraceable. The guards are
now `(?<![\w-])` / `(?![\w-])`, so a standalone `482913` is still redacted while
UUIDs survive. Regression-tested both ways.

### D-021 — No component tests yet
Backend auth is covered end-to-end with a mocked verifier (the phase-1
criterion), and the API client's token-vs-demo precedence is unit-tested. The
`AuthProvider`/guard components are verified manually for now; adding
`@testing-library/react` is deferred to phase 11 rather than widening phase 1.

---

## Phase 0 (v2)

### D-022 — The customer UI is a native SwiftUI app; the website is laptop-only
Build plan v2 replaces the React phone shell with a native iPhone app and
reduces the website to the lender and compliance dashboard plus the receipt
check. The backend is unchanged and now serves both, which is what makes this
affordable: the journey is server-driven, so the state machine, the loan maths
and the consent lock are written once and both clients only render what the
backend returns.

Consequences recorded elsewhere in this file: the phone components were deleted
from the website (D-023), the error format became a shared contract rather than
a FastAPI default (D-025), and the fixtures in `contracts/` now bind three
codebases together (D-030).

This **supersedes** the v1 reading of §5 for anything phone-shaped. Everything
in D-001 … D-021 still holds unless named below.

### D-023 — The website's phone routes were deleted, not hidden
`PhoneFrame`, `PhoneLayout`, `SafeArea`, the phone `ConceptRibbon` and
`HomePlaceholder` are gone, and with them the `RequireAuth` guard that only
phone routes used. Leaving a second, half-maintained customer UI alive would
have meant every journey change needed doing twice, and the one that was not
demoed would quietly rot.

The website now has four routes: `/` (redirect), `/login`, `/dashboard/*` and a
catch-all. A v1 phone URL lands on the 404, which explains that the customer
journey is in the iPhone app.

`Logout` moved into the dashboard sidebar, because `HomePlaceholder` had been
the website's only sign-out button.

### D-024 — The dashboard sidebar carries the signed-in identity
Partly practical (see D-023) and partly a compliance point: a dashboard showing
other people's journeys should always say who is looking at it.

### D-025 — One error envelope, enforced by exception handlers
Every failure is `{"error": {"code", "message", "requestId"}}` (§8.1), installed
as handlers for `ApiError`, `HTTPException`, `RequestValidationError` and bare
`Exception`. Handlers rather than per-route discipline, because the errors that
matter most — a 404 on an unknown path, a 422 from validation — never reach a
route.

Three v1 tests asserted FastAPI's `{"detail": ...}` and were updated. `deps.py`
now raises `ApiError` directly so the code is explicit rather than derived from
the status.

`validation_error` never echoes the rejected value: it may be a transcript.

### D-026 — Request IDs live in a `ContextVar`
A log line emitted inside the journey engine can name its request without
threading a `Request` through every function. An inbound `X-Request-ID` is
reused (so one id can span app and backend) but only after matching
`^[A-Za-z0-9._:-]{1,64}$` — it is echoed into a response header and into logs,
so a caller must not be able to inject control characters.

### D-027 — Rate limiting is an in-process token bucket
One uvicorn worker on a laptop, so a shared store would add failure modes with
no benefit; Redis is the production answer and is recorded as a residual risk in
`SECURITY.md`.

A token bucket rather than a fixed window because the demo is bursty: three
quick replies in a second is legitimate, a script hammering `/voice` is not.
Keyed by user id when signed in and client IP otherwise, so one noisy visitor
cannot exhaust a customer's budget mid-journey. The IP comes from
`request.client.host`, never from `X-Forwarded-For` — uvicorn only honours
forwarded headers from 127.0.0.1, and reading the header ourselves would let any
caller choose its own identity.

### D-028 — Body limits are raw ASGI middleware
`BaseHTTPMiddleware` materialises the whole body before handing it on, so a
limit enforced there would already have buffered what it was meant to refuse.
`Content-Length` is checked first; a chunked body without one is counted as it
streams. 64 KB for JSON, 2 MB for the audio upload paths.

### D-029 — `make secret-scan` falls back to its own patterns
`gitleaks` is not installed on this machine and installing a global tool is not
ours to decide (same reasoning as D-002). The scanner uses `gitleaks` when it is
on `PATH` and otherwise applies the §13.3 patterns to **tracked** files — a
secret only matters once it is staged or committed, and scanning the working
tree would drown in `node_modules`.

It runs inside `make lint` and as a `.githooks/pre-commit` hook, enabled by
`make setup`. Findings print the location only, never the matched text: printing
it would copy the secret into the terminal and the scrollback.

Two files are exempt: the scanner (it contains every pattern by definition) and
`BUILD_PLAN.md` (it documents the patterns and the variable names). A single
line can opt out with the marker `spasht-secret-scan:allow`.

### D-030 — Contract fixtures compare shape, not values
`make contracts` regenerates `contracts/fixtures/*.json` from the live app;
every other test run verifies that each committed fixture still has the field
structure the backend produces. Only the structure is compared — ids and
timestamps change every run, and a fixture that re-diffed constantly would train
everyone to ignore it.

The iOS test target references `contracts/fixtures` as a **folder reference**
rather than copying it in: `ENABLE_USER_SCRIPT_SANDBOXING` (correctly) forbids a
build script from writing into the source tree, and a folder reference also
means a newly generated fixture is picked up without regenerating the project.

### D-031 — Two Info.plists rather than one generated file
App Transport Security needs a real boolean, and an `$(VARIABLE)` substituted
into a plist produces a string — so `NSAllowsLocalNetworking` cannot be switched
per configuration from the xcconfigs. `Info-Debug.plist` and
`Info-Release.plist` are therefore separate files selected by `INFOPLIST_FILE`.

They are identical except that Release has **no ATS block at all**: a Release
build reaches the backend over HTTPS through the tunnel or not at all. Every
value that varies by machine comes from the xcconfigs, so there is nothing
machine-specific to drift, and `AppConfigTests` asserts the keys the app reads.

### D-032 — The demo key cannot ship, for two independent reasons
`Release.xcconfig` blanks `DEMO_AUTH_KEY` *after* including `Secrets.xcconfig`,
so whatever a developer has locally, a Release build has none. Separately, the
demo UI is inside `#if DEBUG`. Either alone would do; both means a mistake in
one is not enough to leak it. `Settings.demo_auth_allowed` on the backend also
requires a non-empty key, so an empty one cannot match an empty header.

### D-033 — The Simulator is chosen by UDID, not by name
`make ios-build` originally passed `name=iPhone 17 Pro`, which fails: that model
exists only on the iOS 26.5 runtime while `OS:latest` resolves to 27.0.
`scripts/ios-sim.sh` resolves a concrete UDID — the requested name if present,
otherwise the newest available iPhone — and all three iOS targets share it.

Related: the Simulator **GUI** app is not where Xcode used to install it on this
machine, so `make ios-run` boots the device headlessly and prints a note.
Install, launch, screenshots and tests all work without the window.

### D-034 — `make keys` exists now, but generates no signing keypair yet
Phase 1's hardened demo auth needs `DEMO_AUTH_KEY`, and the plan only lists
`make keys` from phase 2. It is implemented now for the env-file secrets
(`TRANSCRIPT_KEY`, the three peppers, `TTS_CACHE_SECRET`, `DEMO_AUTH_KEY`). The
Ed25519 receipt-signing keypair needs PyNaCl and arrives with the trust layer in
phase 6; the script says so rather than pretending.

It never overwrites a value that is already set — regenerating `CUSTOMER_REF_PEPPER`
would silently invalidate every receipt already issued — and never prints a
value, because the terminal is often on a projector.

---

## Phase 1 (v2)

### D-035 — Demo auth needs four conditions, not two
v1 honoured `X-Demo-User` whenever `DEMO_AUTH=true` and `APP_ENV=dev`. During a
demo the API is reachable from the internet through the ngrok tunnel, which made
that one header away from a session.

It now also requires a non-empty `DEMO_AUTH_KEY` and a matching `X-Demo-Key`,
compared with `hmac.compare_digest` so the key cannot be recovered by timing.
The first three conditions are the environment's decision; the fourth is the
caller's, and it is the only one an attacker cannot satisfy by finding the URL.

The path is rate-limited **before** the key is checked (60/min/IP), so guessing
is slow, and every refusal returns the same message — which condition failed is
exactly what a prober wants to learn. Tested by breaking each condition on its
own and by asserting all four refusals are byte-identical.

### D-036 — `demo-admin` is a separate identity from `sunita`
§13.2 names two demo identities. `sunita` is the customer the iPhone app signs
in as; `demo-admin` is the dashboard operator the website signs in as, and it
has **no persona** because an operator has no journey.

The website previously signed in as `sunita`, which would now show a customer
with no admin rights on a dashboard. `demo-admin` still has to be on
`DASHBOARD_ADMIN_EMAILS` — the identity alone grants nothing — so
`demo-admin@spasht.invalid` was added to the local `backend/.env`. All demo
addresses use `.invalid`, which RFC 2606 reserves, so none can ever reach a
real mailbox.

### D-037 — Admin requires a **verified** email
`is_admin` is now `email_verified AND email in DASHBOARD_ADMIN_EMAILS`. Anyone
can put an address into a profile; only Google can mark it verified. Without the
check, the allowlist admits whoever *claims* one of its addresses, which is no
barrier at all.

`users.email_verified` is stored (migration `0003_user_session`) and refreshed on
every request alongside `is_admin` (D-014), so verifying an address grants access
on the next request rather than at the next login. Existing rows default to
`false`, which is the safe direction: a current admin signs in again.

### D-038 — `/api/me` changed shape, and `extra="forbid"` makes that loud
v2 §8.2 fixes the response as
`{uid, email, displayName, photoUrl, preferredLanguage, isAdmin, session, persona}`.
Renames from v1: `id` → `uid`, and `personaId` → a nested `persona` object.
`persona` is an object from the start, with its other fields null, so phase 2
filling in the masked name and city does not change the shape clients decode.

`session` is returned so the demo badge is driven by the server's answer rather
than the client's own state — in v1 the badge could disagree with reality
(D-016). Now it cannot.

`MePatch` uses `extra="forbid"` (§13.5), so `PATCH /api/me {"isAdmin": true}` is
a 422 rather than a silent no-op. This **amends D-014**, which said such a field
is "simply ignored": ignoring it looks to the caller like it worked. The field is
still never honoured; it is now also never accepted.

### D-039 — `Auth.auth()` is only ever reached through one guard
**Found by running the app, not by a test.** `AuthService.start()` installed a
token provider that called `Auth.auth().currentUser`. On a machine with no
`GoogleService-Info.plist` Firebase is never configured, and `Auth.auth()`
**traps** in that state — it is not a throwing API, so there is no recovering at
the call site. The first demo request therefore crashed the app on launch: the
one path that is supposed to work without Firebase was the one that could not.

Every access now goes through `AuthService.currentFirebaseUser()`, which returns
nil when `FirebaseApp.app()` is nil, and `GoogleSignInService.signOut()` guards
the same way. `AuthServiceTests` runs in exactly that configuration — the test
bundle has no plist — and asserts both the guard and that `start()` always
reaches a terminal state, since a view stuck on `.starting` is the blank screen
the crash produced.

### D-040 — The Google button carries no Google logo
§5.1 forbids third-party logo artwork anywhere in this concept, and that rule
does not get an exception for the sign-in button: reproducing someone else's
mark is the thing it exists to prevent. The button keeps the standard white
surface, 48 pt height and "Continue with Google" wording, with an SF Symbol in
place of the mark.

### D-041 — The iOS app holds no business logic, including about itself
`isAdmin`, the persona, the language and the session kind all come from
`/api/me`. The app has no notion of what an admin is; it renders what the
backend decided. The same applies to the website, whose route guard is cosmetic
on top of the backend's own 403 (plan rule 10).

### D-042 — `make ios-run` cannot show the app on this machine
Xcode 27 does not install `Simulator.app` where previous versions did, and it is
not present anywhere on this machine. `simctl` boots the device headlessly, so
building, installing, launching, screenshotting and testing all work — but the
scene never becomes `.active`, so anything behind a tap cannot be driven from
the command line, and the privacy cover (§5.10) shows instead of the real
screen.

Consequence: the login screen was verified by screenshot, and everything behind
it was verified through the API and the test suites. Checking the signed-in
screen visually needs Xcode's ▶ button. Installing the Simulator component is in
the human steps.
