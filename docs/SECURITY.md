# Security

What is actually implemented, what is deliberately not, and what production would
need. Kept current at the end of every phase (build plan §13).

**Posture:** "pretty good for a prototype". Real controls where they matter, and
documented gaps everywhere else. All data is synthetic but is treated as if it
were real — that is the only way the controls get exercised.

**Status:** phases 0 and 1 complete. Sections marked ⬜ land with the phase that builds
the thing they protect.

---

## 1. What we protect, and from whom (§13.1)

| Asset | Threat | Controls | Status |
|---|---|---|---|
| Sarvam API key and credits | Leak through git, the app bundle or logs; abuse through the tunnel | Key only in `backend/.env`; secret scan + pre-commit hook; never logged; clients never call Sarvam | ✅ key handling · ⬜ rate limits on voice (phase 7) |
| Receipt integrity | Someone edits a receipt or the database | Hash chain + Ed25519 signature + append-only triggers + daily Merkle anchor | ⬜ phase 6 |
| Customer data | Another user reads someone's journey or receipt | Token auth, ownership checks returning 404, masked fields, encrypted transcripts | ⬜ phases 2–3 |
| Admin dashboard | Non-admins get in | Server-side admin check on every route; verified-email allowlist | ✅ |
| Backend exposed through ngrok | Strangers calling the API | Auth on everything except health/public receipt/audio; hardened demo auth; rate limits; body limits | ✅ |
| LLM behaviour | Prompt injection through speech; invented numbers | Structured outputs, code decides transitions, Number Guard, user text treated as data | ⬜ phase 8 |

---

## 2. Identity and access (§13.2)

**Done**
- Firebase ID tokens are verified on every protected route — signature, `aud` =
  `FIREBASE_PROJECT_ID`, issuer and expiry — via `firebase_admin`, falling back
  to `google-auth`'s `verify_firebase_token` on machines with no ambient
  credentials (D-013). The fallback checks the same things.
- `is_admin` is recomputed from `DASHBOARD_ADMIN_EMAILS` on every request and is
  never client-settable (D-014). Removing an email revokes access on the next
  request.
- 401 responses carry one generic message for every failure mode, so they are
  not a probing oracle. The real reason is logged.
- **Demo auth needs four conditions** (D-035): `DEMO_AUTH=true`, `APP_ENV=dev`,
  a non-empty `DEMO_AUTH_KEY`, and a caller `X-Demo-Key` matching it via
  `hmac.compare_digest`. Rate-limited (60/min/IP) **before** the key is checked,
  so guessing through the tunnel is slow. Every refusal returns one identical
  message; tested by breaking each condition alone and asserting the four
  responses are byte-identical.
- **Admin requires a verified email** (D-037): `email_verified AND email in
  DASHBOARD_ADMIN_EMAILS`. Anyone can put an address in a profile; only Google
  can mark it verified.
- **Two demo identities** (D-036): `sunita` (customer, iOS) and `demo-admin`
  (dashboard, website, no persona). Both still need the allowlist to be admins.
  All demo addresses use RFC 2606 `.invalid`, so none can reach a real mailbox.
- `users.email_verified`, `session_kind` and `last_login_at` are stored, so the
  dashboard and audit log can tell a real session from a demo one.

**Open**
- ⬜ `actor=demo` audit entries (phase 3, when `audit_log` exists).
- ⬜ Per-resource ownership checks returning **404**, never 403, so a wrong id
  and someone else's id are indistinguishable (phase 3).

---

## 3. Secrets (§13.3)

| Secret | Lives in | Never in |
|---|---|---|
| `SARVAM_API_KEY` | `backend/.env` | App, website, git, logs, LLM prompts |
| `DEMO_AUTH_KEY` | `backend/.env`, `ios/Config/Secrets.xcconfig` (Debug), `frontend/.env` (dev) | Git, Release builds |
| `TRANSCRIPT_KEY`, `CUSTOMER_REF_PEPPER`, `OTP_PEPPER`, `TTS_CACHE_SECRET`, Ed25519 private key | `backend/.env`, `backend/secrets/` (mode 600) | Git, logs |
| `GoogleService-Info.plist` | `ios/SpashtPaytm/Config/` | Git |
| Firebase web config | `frontend/.env` | Git (not truly secret, but kept out) |

**Done**
- `make keys` generates the env-file secrets, **never overwrites** an existing
  value, **never prints** one, and chmods `backend/.env` to 600 (D-034).
- `make secret-scan` uses `gitleaks` when installed and otherwise applies the
  §13.3 patterns to tracked files (D-029). It runs inside `make lint` and as
  `.githooks/pre-commit`, enabled by `make setup`.
  - **Verified in phase 0:** a staged file containing a fake `sk_` key was
    refused by the hook, and the commit did not happen.
  - Findings print the location only, never the matched text.
- `.env.example` and `Secrets.example.xcconfig` contain only empty values.
- Gitignored: `.env*` (except `.env.example`), `backend/secrets/`,
  `ios/Config/Secrets.xcconfig`, `ios/SpashtPaytm/Config/GoogleService-Info.plist`,
  `docs/reference/`, `docs/screens/`.

**After the event:** rotate the Sarvam key and the demo key.

---

## 4. Transport and network (§13.4)

**Done**
- uvicorn binds **127.0.0.1**, never `0.0.0.0`. The ngrok tunnel is the only way
  in from outside, and only the backend is ever tunnelled — the website stays on
  localhost.
- `--proxy-headers --forwarded-allow-ips 127.0.0.1`: forwarded headers are
  trusted only from the local ngrok agent, so a caller cannot spoof its own IP
  and escape a rate limit.
- CORS is an allowlist from `CORS_ORIGINS` (`http://localhost:5173`), never `*`.
  The native app is not subject to CORS.
- HSTS is added when the request arrived over HTTPS.
- The app sends `ngrok-skip-browser-warning: 1` on every request.
- ATS: the Debug plist allows HTTP to **localhost only**; the Release plist has
  no ATS exceptions at all (D-031).

---

## 5. Input validation and abuse limits (§13.5)

**Done**
- Body limits as ASGI middleware, checked before the body is buffered (D-028):
  64 KB for JSON, 2 MB for audio paths. Over the limit → 413 `upload_too_large`
  in the standard envelope.
- Token-bucket rate limiter (D-027) with the §13.5 policy table. Over the limit
  → 429 with `Retry-After`.

**Open**
- ⬜ Apply the limiter to the remaining routes as they are built (phases 3, 6, 7).
- ⬜ Pydantic models with `extra="forbid"`, enums and length caps (phase 3).
- ⬜ Audio magic-byte validation → 415 (phase 7).

| Route | Limit | Applied |
|---|---|---|
| `/journeys/{id}/voice` | 20 / min / user | ⬜ phase 7 |
| `/journeys/{id}/turn` | 60 / min / user | ⬜ phase 3 |
| `/otp/verify` | 5 per 10 min per journey | ⬜ phase 3 |
| `/receipts/*/verify-candidate` | 20 / min / user | ⬜ phase 6 |
| `/r/*`, public `/receipts/*` | 60 / min / IP | ⬜ phase 6 |
| Any demo-auth request | 60 / min / IP | ✅ phase 1 |

---

## 6. OTP (§13.6) — ⬜ phase 3

6 digits from `secrets.randbelow`, stored as HMAC-SHA256 with `OTP_PEPPER`,
compared in constant time. 5-minute expiry, 3 attempts then locked. Never
logged, never spoken, never requested by voice. `demoCode` is returned only when
`OTP_DEMO=true` **and** `APP_ENV=dev`.

---

## 7. AI safety (§13.7) — ⬜ phase 8

Customer speech is untrusted data wrapped in `<customer_said>` tags; LLM output
must match a JSON schema or it is discarded; code decides every transition; the
Number Guard rejects any generated text containing a number that is not a KFS
fact; the LLM sees only this journey's facts, the first name and the language.

---

## 8. Data protection (§13.8)

**Done**
- Synthetic data only.
- `PiiRedactionFilter` on the root logger (D-010) covers PAN, Aadhaar-like runs,
  Indian mobiles, emails, bearer tokens and standalone 6-digit OTPs. It does not
  match inside UUIDs (D-020), so `user_id` and `journey_id` stay traceable.
  Rupee amounts and percentages are deliberately not redacted: they are product
  facts needed to debug the Number Guard, and are not personal data.
- Validation errors never echo the rejected value — it may be a transcript.

**Open**
- ⬜ Transcripts encrypted with AES-256-GCM (phase 6).
- ⬜ `customer_ref` as an HMAC of the user id (phase 6).
- ⬜ Masking in the UI and on receipts (phases 2, 6).

**Production policy, not implemented:** consent records retained for 1 year
after the contract ends, as RBI requires.

---

## 9. Database (§13.9)

**Done:** all queries go through SQLAlchemy parameters; no SQL is built from
strings with user input.

**Open:** ⬜ append-only triggers on `receipts`, `consents`, `audit_log` and
`teachback_attempts` (phase 2); ⬜ `demo-reset` restricted to dev + admin
(phase 2).

**Production note:** the app's DB role would hold only `INSERT, SELECT` on the
four evidence tables. `TRUNCATE` is used only by the dev-only `make demo-reset`.

---

## 10. Headers (§13.10)

**Done** — on every response, including errors (`SecurityHeadersMiddleware`):

```
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'
X-Request-ID: <16 hex chars>
```

- The public receipt page `/r/*` gets the stricter
  `default-src 'none'; style-src 'unsafe-inline'; img-src data:` (§11.6); the
  dev-only `/api/docs` gets a relaxed policy so Swagger UI renders.
- `Server` is suppressed with uvicorn's `--no-server-header`; middleware cannot
  remove it because uvicorn appends it below the ASGI layer.

**Open:** ⬜ the website's own CSP meta tag, verified against Firebase sign-in
(phase 1).

---

## 11. iOS (§13.11)

**Done**
- No secrets in the bundle beyond the non-secret Firebase config and the
  Debug-only demo key.
- The demo key cannot ship for two independent reasons (D-032): Release blanks
  `DEMO_AUTH_KEY` after including `Secrets.xcconfig`, and the demo UI is inside
  `#if DEBUG`.
- Privacy cover whenever `scenePhase != .active`, so the app switcher never
  shows journey data. It deliberately does **not** react to recording or
  mirroring — the demo mirrors the iPhone to the laptop.
- `NSMicrophoneUsageDescription` present; the mic is requested only on first
  use, and typing always works if it is denied.

- **Release verified in phase 1:** the built `Info.plist` has an empty
  `DemoAuthKey` and no `NSAppTransportSecurity` block, and `strings` on the
  binary finds no demo UI text. The whole of `DemoAuth.swift` is inside
  `#if DEBUG`.
- **Tokens are never stored by us.** Firebase keeps them in the Keychain; the
  app asks for a fresh one per request and never writes one to `UserDefaults`.
  `Auth.auth()` is reached only through one nil-guard (D-039).

**Open:** ⬜ re-check the Release binary after every phase that touches auth
(phase 12 security review).

---

## 12. Supply chain (§13.12)

**Done:** exact version pins with committed lockfiles —
`backend/pyproject.toml` + `requirements.lock`, `package-lock.json`, and
`Package.resolved` inside the committed Xcode project. Only FirebaseAuth and
GoogleSignIn are allowed as iOS packages.

**Done (phase 12):** `make audit` runs both. The review on 2026-10-31 found
**23 advisories across 7 Python packages** and **4 high-severity advisories** in
the website's tree. What was done with each:

| Package | Was | Now | Note |
|---|---|---|---|
| `cryptography` | 46.0.3 | **50.0.0** | 7 advisories cleared, including GHSA-537c-gmf6-5ccf |
| `pynacl` | 1.6.0 | **1.6.2** | PYSEC-2026-3002; this signs every receipt |
| `python-multipart` | 0.0.20 | **0.0.31** | 6 advisories; it parses the voice clip and the KFS upload |
| `pdfplumber` / `pdfminer.six` | 0.11.7 / 20250506 | **0.11.10 / 20260107** | 2 advisories in the PDF reader an admin feeds untrusted files to |
| `pydantic-settings` | 2.13.0 | **2.14.2** | GHSA-4xgf-cpjx-pc3j |
| `pytest` | 9.0.1 | **9.0.3** | dev only |

**23 → 5.** All 221 backend tests pass on the upgraded set, and the pins in
`pyproject.toml` were moved to match, so the lockfile and the audit agree.

**Accepted, with reasons:**

- **`starlette` 0.49.3 — 5 advisories.** Every fix is in the 1.x line, and
  `fastapi` does not permit it: tried, and FastAPI 0.162.0 (the latest) still
  resolves 0.49.3. Upgrading is upstream's decision, not ours. What stands
  between those advisories and us: the body-size middleware rejects an oversized
  body *before* Starlette buffers it (D-028), multipart parsing is
  `python-multipart` 0.0.31 rather than Starlette's own, every route is rate
  limited, and the tunnel is only open during a rehearsal or the demo itself.
- **4 high-severity advisories in `@grpc/grpc-js`,** reached only through
  `@firebase/firestore`. The website imports `firebase/app` and `firebase/auth`
  and **never constructs a Firestore client**, so the vulnerable code path is
  not reachable. `npm audit fix --force` would downgrade `firebase` to 9.14.0 —
  a breaking change that would take Google sign-in with it. Not taken.

---

## 13. Residual risks (accepted for a prototype)

1. **Rate limits are per process and in memory** (D-027). Restarting the backend
   clears every bucket; two workers would not share state. Production: Redis.
2. **No CSRF tokens.** The API is token-authenticated with no cookies, so there
   is nothing for a cross-site request to ride on.
3. **Demo auth exists at all.** Narrowed by three required conditions plus a
   shared key, dev-only, rate-limited and audited — but it is still a
   non-Firebase way in. It must never run with `APP_ENV=prod`.
4. **The tunnel exposes the backend to the internet** while it is running. Auth
   covers everything except health, audio (unguessable HMAC keys) and the public
   receipt page. Stop the tunnel after the event.
5. **Five `starlette` advisories stay open** because FastAPI pins it below the
   fixed line (see §12).
6. **`gitleaks` is not installed here,** so the scan uses our own smaller
   pattern set (D-029). It catches the shapes we actually handle; it is not a
   general-purpose scanner.
7. **A free Apple Personal Team expires after 7 days,** so the app must be
   reinstalled the night before the event.

---

## 14. Rescue agent (phase 10)

The rescue agent is the one feature that can reach *out* to a customer, so it is
the one with a hard "when not to" rule rather than only an authorisation rule.

**Done**
- **Ownership, not visibility.** `GET /rescue/pending` selects only tasks whose
  journey has `user_id = caller`; accept and decline join through `journeys`
  with the same predicate in the query, and answer **404** for anyone else's
  task (§13.2). There is no code path on which another customer's task is
  loaded into memory.
- **Three contact gates, re-checked on every poll** (D-044): DND first and
  unconditionally, then `consent_callbacks`, then `CONTACT_WINDOW` evaluated in
  IST. A task that fails them is still created, with `contact_window_ok = false`
  and a reason, so the dashboard can explain the silence.
- **One task per journey, ever** — enforced by a `NOT EXISTS` in the scheduler's
  query — and declining closes the task server-side, so nobody is rung twice
  about the same application.
- **Rate limited** on all three routes (the `turn` bucket, 60 / min / user); a
  15 s poll uses four of them.
- **No personal data on the wire or in the audit row.** The call carries the
  template line, the step and the task id; `audit_log.data` carries the idle
  seconds and the decision reason.
- **Nothing is dialled.** The call is an in-app screen labelled
  "Concept demo · simulated call" (D-043).

**Residual risk**
- `CONTACT_WINDOW` is a single window in IST, with no per-customer timezone and
  no holiday calendar. For a demo with synthetic personas in Maharashtra that is
  honest; a real deployment would need both, plus the national DND registry
  rather than a column.

---

## 15. The phase-12 security review (2026-10-31)

§13 checked end to end rather than as a list of intentions. What was verified,
and how.

### 15.1 Supply chain
See §12. 23 Python advisories reduced to 5, all upstream-blocked; the website's
4 are unreachable code paths with a breaking "fix". `make audit` is now a
command, so the next check is one line rather than a research exercise.

### 15.2 The iOS Release build carries no demo path
`make ios-build CONFIG=Release` succeeds, and the resulting binary was searched
for the demo session's fingerprints:

```
strings SpashtPaytm.app/SpashtPaytm | grep -icE 'X-Demo-User|demo-admin|Continue as demo'
0
```

Zero. `DemoAuth`, the demo header plumbing and the "Continue as demo user"
button are inside `#if DEBUG`, so a Release build cannot authenticate without
Firebase even if the backend would allow it. `ENABLE_TESTABILITY = NO`,
`SWIFT_OPTIMIZATION_LEVEL = -O`, and `DEMO_AUTH_KEY` is empty in
`Config/Release.xcconfig`.

### 15.3 Rate limits are applied, not merely configured
Every route that costs money or advances state enforces a bucket:
`/journeys/{id}/voice` (20/min/user), `/journeys/{id}/turn` (60/min/user),
`/otp/verify` (5 per 10 min per journey, 3 attempts per code),
`/receipts/*/verify-candidate` (20/min/user), the public receipt pages and audio
(60/min/IP), every demo-auth request (60/min/IP), and the phase 10 and 11 routes
on the `turn` bucket. `tests/test_ratelimit.py` asserts the policy table and the
`Retry-After` header.

### 15.4 Ownership returns 404, never 403
Asserted for every resource a customer can own, in each case with the predicate
**inside the query** so another user's row is never loaded into memory:

| Resource | Test |
|---|---|
| A journey | `test_journey.py` |
| A voice turn on someone else's journey | `test_failure_paths.py` |
| A receipt detail | `test_trust.py` |
| A rescue task (pending, accept, decline) | `test_rescue.py` |
| A KFS document (admin-only, so 403 for a customer) | `test_kfs_ingestion.py` |

### 15.5 Failure handling
`tests/test_failure_paths.py` makes each link in the chain fail on purpose and
asserts the degradation: speech-to-text failing still returns a turn with the
"didn't catch that" line; text-to-speech failing leaves every caption on screen
with a null `audioUrl`; the LLM timing out falls back to the rules and the
seeded templates; a non-audio upload is 415 and an oversized one is 413, both
before anything is forwarded to a paid API; an expired token is a 401 with one
generic message, so the app ends the session and the message is no oracle; and
`/health` answers 200 `degraded` even when the database check itself raises.

On the phone: a denied microphone is not an error state but a sentence pointing
at the keyboard, which is always beside the mic (§5.9).

### 15.6 What this review did not cover
- **No penetration test, and no fuzzing** of the multipart or PDF paths beyond
  the magic-byte checks and the size caps.
- **No review of the Sarvam account's own posture** — key scope, rotation
  policy, what their logs retain.
- **The dashboard's SSE stream is not rate limited.** An admin holding many
  connections open could exhaust the queue set; the bus drops the oldest event
  per subscriber rather than blocking, so the blast radius is a stale dashboard
  rather than a stalled turn.
- **`gitleaks` is still not installed here** (D-029), so the secret scan is our
  own smaller pattern set.
