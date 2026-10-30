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

**Open:** ⬜ `npm audit` and `pip-audit` in phase 12.

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
5. **Transcripts are plaintext until phase 6.**
6. **`gitleaks` is not installed here,** so the scan uses our own smaller
   pattern set (D-029). It catches the shapes we actually handle; it is not a
   general-purpose scanner.
7. **A free Apple Personal Team expires after 7 days,** so the app must be
   reinstalled the night before the event.
