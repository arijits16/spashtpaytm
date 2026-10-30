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

### D-043 — The rescue call is an in-app screen, not a real telephone call
§9 describes an agent that rings a customer back. In production that call would
be placed by a telephony provider — Exotel in India, Twilio elsewhere — which
would dial the masked number, stream the `rescue_call` line and hand the leg to
the journey. None of that is in this build.

What is here instead: the backend raises a `rescue_tasks` row, the iPhone polls
`GET /rescue/pending` every 15 s while in the foreground, and a full-screen
incoming-call view appears. Accept plays the cached `rescue_call` audio and
resumes the journey at the exact step.

Why not the real thing: a telephony account needs a verified business entity, a
DLT-registered sender and a per-minute budget, none of which a hackathon
concept should be spending on a path that demos identically. The screen says
"Concept demo · simulated call" and the footer says a real deployment would use
a telephony provider, so nobody watching can mistake which it is.

### D-044 — The contact window is re-checked when the phone polls, not only when the task is raised
`rescue_tasks.contact_window_ok` records what was true at creation, because the
dashboard has to be able to explain why a task exists and no call was placed.
It is **not** the gate. `may_contact` runs again on every poll, so a task raised
at 17:59 stops ringing at 18:01, and setting DND or withdrawing the consent to
callbacks takes effect on the next poll rather than on the next task.

The three conditions, in the order that respects the customer most: DND first
and unconditionally (their own standing instruction, whatever the hour),
then the consent to callbacks, then the clock.

Declining is a server-side state change (`POST /rescue/{id}/decline` → status
`closed`), not a client-side dismissal. A task left open would ring again
fifteen seconds later, which is exactly the harassment the window rules exist to
prevent.

### D-045 — The rescue agent publishes its SSE events from the event loop, not from its worker thread
`tick` is synchronous SQLAlchemy and runs in `asyncio.to_thread`, so it must not
touch the event bus: the bus hands events to `asyncio.Queue`s owned by the main
loop, and `put_nowait` from another thread can leave a connected dashboard
un-woken. `tick` therefore returns the payloads it created and `run_forever`
publishes them once the thread has finished.

### D-046 — The KFS extraction asks for strings and parses them ourselves
The Document Intelligence schema types every field `string`, even the amounts. A
KFS writes "INR 4,600", "18.67% (reducing balance)" and "4% of principal
outstanding"; asking the model for a number asks it to read *and* parse, and a
parse failure then arrives as a confident wrong figure rather than as a blank.

`kfs/parse.py` does the parsing, where the rules are a dozen lines a reviewer
can check and the failure mode is `None` → "could not read" on the dashboard for
a human to fill in.

### D-047 — Extraction falls back to `pdfplumber`, and says which engine read the document
Document Intelligence is a remote call on venue Wi-Fi. The offline reader
matches the label/value rows of an RBI-format KFS, so `make demo-reset` and the
KFS library still do something real with no network (§10.6) — and two
independent readings that agree is worth more than one confident reading.

The engine is shown on every row and in the detail pane, with the offline
reader's confidence deliberately fixed lower (0.55) than anything the model
returns: a regex over a label is a weaker reading than a model that saw the
page, and the dashboard sorts a human's attention by confidence.

The watermark needed handling. `pdfplumber` reads the diagonal SAMPLE as stray
one- and two-character lines, and sometimes *inside* a line ("Recovery
practicSes"), so clause titles are matched by similarity rather than equality
and very short lines are dropped.

### D-048 — Generated teach-back text may not contain a single digit
The model writes `{LATE_FEE}`; code fills it from the verified facts at render
time, exactly as the seeded rows work. Enforced by rejecting any text containing
a digit — Latin or Devanagari — rather than by relying on the Number Guard
alone, because the guard *allows* a number that matches a fact. "Rs 50,000"
passes the guard when the principal is 50,000, and is then quoted unchanged to
the customer who asked for 75,000: questions are rendered per journey from
scaled facts. A placeholder has neither problem, and survives a KFS revision.

Two more validations earned their place by failing in practice:

- **No placeholder more than twice in one line.** Asked to use placeholders
  instead of numbers at temperature 0.2 with no penalty, the model looped on the
  token: one measured run produced nine consecutive `{LATE_FEE}`s and then ran
  out of budget. `frequency_penalty: 0.6` removed it entirely; this check
  catches it anyway.
- **The three languages must use the same placeholders.** One run wrote an
  option as "your monthly payment is {EMI}" in English and "{PRINCIPAL}" in
  Marathi — two different claims presented as one option, in a product whose
  whole premise is that the customer understood what they agreed to.

### D-049 — Reasoning is off for offline generation too
§10 requires reasoning off for live turns. Measured, it has to be off offline as
well: asked for one teach-back question with reasoning on, `sarvam-105b` spent
3,999 reasoning tokens and returned **no content at all** — a truncated reply
the schema then discarded, which looks exactly like a model that cannot follow
instructions. Three short sentences in three languages need no chain of thought.

Offline calls do get their own timeout class (180 s read): nobody is waiting on
the four-second voice budget, and the 20 s live timeout failed every time.

### D-050 — Publishing a KFS is two calls, and re-prices the offer from our own arithmetic
`POST /admin/kfs/{id}/publish` with `confirm: false` generates the questions and
lines, guards them and stores the proposal; `confirm: true` activates what was
reviewed. That is the "→ review →" in the plan's "generate → guard → review →
activate", and it is why no single action can put model-written text in front of
a customer.

Activation re-prices the offer with `loan_math.quote` rather than with the EMI
and totals extracted from the PDF. The extracted ones were verified and are
shown, and a disagreement is reported by the sanity checks — but the catalogue
stores what the code computes, because that is the arithmetic a receipt is
verified against, and the two must never be able to differ.

The seeded questions are deactivated, not deleted, so `make seed` puts the demo
back. A publish is reversible.

### D-051 — The iOS voice loop was missing, and phase 12 could not be done without it
Phase 7 shipped the backend's ears and mouth, and the app's mic button was still
the phase-6 placeholder reading "Voice comes in Phase 7". There was no
`AVFoundation` in the app at all: no recorder, no playback, and
`onReplay: { /* phase 7 plays the audio */ }` in `JourneyView`.

That made three phase-12 requirements unreachable (mic denied, speech-to-text
error, text-to-speech error) and phase 13's "the golden path runs on a real
iPhone **by voice**" impossible, so it was built here:

- `AudioRecorder` — AAC in m4a, 16 kHz mono (what `stt.detect_format` accepts by
  magic bytes, and what the phone encodes in hardware), 25 s ceiling matching
  §10.1, level metering so the button grows while the phone is hearing, and a
  typed `Failure` per case. Nothing is kept: the clip goes to the caller as
  `Data` and the temporary file is deleted immediately (§13.11).
- `SpeechPlayer` — one player for the whole app, replacing the rescue call's
  private one. Lines **queue** rather than interrupt, because EXPLAIN_KFS speaks
  three of them and playing only the last would drop two thirds of the
  explanation. Bytes come through `APIClient` so the tunnel header is present;
  without it ngrok serves its HTML interstitial and `AVAudioPlayer` fails
  silently. The audio session is `.playback`/`.spokenAudio`, so a phone on
  silent still speaks.
- `APIClient.upload` — multipart by hand. It is one file part and two text
  fields; a dependency on the critical path of the product's main interaction is
  the worse trade.

A denied microphone is not an error state. It is a sentence pointing at the
keyboard, which is always beside the mic (§5.9).

### D-052 — Five starlette advisories are accepted because FastAPI will not allow the fix
The phase-12 `pip-audit` found 23 advisories across 7 packages. Nineteen were
cleared by moving pins forward (cryptography 46.0.3 → 50.0.0, pynacl → 1.6.2,
python-multipart → 0.0.31, pdfplumber/pdfminer.six, pydantic-settings, pytest),
with all 221 tests green on the upgraded set.

The remaining five are in `starlette` 0.49.3 and every fix is in the 1.x line.
FastAPI does not permit it: tried, and FastAPI 0.162.0 — the latest — still
resolves 0.49.3. So the pin was returned to the tested 0.121.2 rather than left
on an untested major for no security gain.

What stands between those advisories and this demo is written down in
`docs/SECURITY.md` §12 rather than left implicit: the body-size middleware
rejects an oversized body before Starlette buffers it, multipart parsing is
`python-multipart` rather than Starlette's own, every route is rate limited, and
the tunnel is open only during a rehearsal or the demo.

The website's four high-severity advisories are in `@grpc/grpc-js`, reachable
only through `@firebase/firestore` — which the site never constructs. The
"fix" downgrades `firebase` to 9.14.0 and takes Google sign-in with it.

### D-053 — Pre-warming is a health ping, not a speculative journey
§10.4 asks for pre-warming. The honest version is a `GET /api/health` at launch
and again on the language screen: it establishes the tunnel connection, the TLS
handshake and the backend's first database connection, costs nothing, and cannot
fail visibly.

The *audio* is pre-warmed where pre-warming actually belongs — `make tts-cache`
on the server, and `SpeechPlayer`'s own cache on the client, which downloads
every line of a turn before it starts speaking and keeps the bytes. The cache
keys are a hash of the text, so a replayed line never costs a second fetch.

What was considered and rejected: starting the journey eagerly from the language
screen to pull the greeting's audio down early. It would warm one more thing and
make the first screen a side effect of a screen the customer had not finished
looking at.

### D-054 — `make ios-config` writes the backend URL, because that is the step that breaks on the day
Phase 13 step 1 was two files to hand-edit after reading what `make tunnel`
printed. One of them is an xcconfig, where `//` starts a comment — so pasting
`https://x.ngrok-free.app` silently stores `https:`, the app then cannot reach
anything, and nothing in the resulting error names the cause. The project has
carried a note about this since phase 0 precisely because it is so easy to hit.

A note is not a fix. `make ios-config` now derives `API_BASE_URL` and
`PUBLIC_BASE_URL` from `NGROK_DOMAIN` in `backend/.env`, escapes the slashes to
`/$()/` with `sed`, tolerates a domain pasted with a scheme or a trailing slash,
and **warns when `backend/.env`'s own `PUBLIC_BASE_URL` disagrees** — because
that is the variable receipt QR codes are built from, and a mismatch means a
judge scanning one reaches the wrong host.

(The first version of the escaping used bash's `${var/a/b}` and emitted literal
backslashes: `http:\/$()\/localhost`. Caught by looking at the file it wrote
rather than by trusting the substitution.)

### D-055 — `make env-check` compares each `.env` with its example
A `.env` created at phase 1 is missing the keys phases 2–12 added, and the
symptom is never "a key is missing". It is the rescue agent using a contact
window nobody set, or a receipt QR pointing at localhost on stage.

Run against this machine it immediately found six real gaps, including
`PUBLIC_BASE_URL` and `NGROK_DOMAIN` absent from `backend/.env` (the phase 13
failure, exactly) and `VITE_DEMO_AUTH_KEY` absent from `frontend/.env`.

It prints names and never values (§13.3), and it never edits anything unless
asked with `--fix`, which appends the missing keys **commented out**: a script
that silently wrote live values into someone's `.env` would be the worse
surprise. It exits 0 either way, because it is a pre-flight report and not a
gate.
