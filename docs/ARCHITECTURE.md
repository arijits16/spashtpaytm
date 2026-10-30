# Architecture

Three clients, one backend, one Postgres. Everything that decides anything lives
in the backend; the clients render what they are given (plan rule 10).

## System

```mermaid
flowchart LR
  subgraph Phone["iPhone - the customer"]
    IOS["Native SwiftUI app<br/>home · journey · voice · receipt"]
  end

  subgraph Laptop["Laptop - lender and compliance"]
    WEB["React website<br/>dashboard · receipt check · KFS library"]
  end

  subgraph Judge["A judge's phone"]
    QR["Scanned QR<br/>/r/{receiptNo}"]
  end

  TUNNEL["ngrok<br/>static HTTPS domain"]
  VITE["Vite :5173<br/>/api proxy"]

  subgraph API["FastAPI :8000"]
    ENGINE["Journey engine<br/>deterministic state machine"]
    TRUST["Trust layer<br/>hash chain · Ed25519 · Merkle"]
    AI["Sarvam clients<br/>+ Number Guard"]
    RESCUE["Rescue scheduler<br/>in-process loop, 15 s"]
    KFS["KFS ingestion<br/>extract · verify · publish"]
    BUS["Event bus<br/>SSE to the dashboard"]
  end

  DB[("PostgreSQL 16<br/>:5433 -> container 5432")]
  SARVAM["Sarvam APIs<br/>Saaras v4 · Bulbul v4 · 105B · Doc AI"]
  FB["Firebase Auth<br/>Google sign-in"]

  IOS --> TUNNEL --> API
  WEB --> VITE --> API
  QR --> TUNNEL
  ENGINE --> DB
  TRUST --> DB
  RESCUE --> DB
  KFS --> DB
  BUS --> WEB
  AI -.-> SARVAM
  ENGINE --> AI
  IOS -.-> FB
  WEB -.-> FB
  API -.->|verify ID token| FB
```

**The Sarvam key exists in exactly one place: the backend.** No client has it,
no client calls Sarvam, and nothing a client sends can choose a model.

## A voice turn, end to end

The product's main interaction, with its latency budget (§10.4) and its failure
behaviour. Every arrow that leaves the backend can fail, and none of them can
stop the journey.

```mermaid
sequenceDiagram
  participant C as Customer
  participant A as iOS app
  participant F as FastAPI
  participant S as Sarvam
  participant P as Postgres

  C->>A: holds the mic, speaks
  A->>A: AVAudioRecorder -> m4a, 16 kHz mono, <= 25 s
  A->>F: POST /journeys/{id}/voice (multipart)
  F->>F: magic-byte check, rate limit, ownership
  F->>S: POST /speech-to-text (saaras:v4)
  S-->>F: transcript + detected language
  Note over F,S: On failure: no transcript, the<br/>engine says "didn't catch that",<br/>typing still works
  F->>F: understanding rules first, LLM only if needed
  F->>F: engine decides the transition (no LLM)
  F->>P: audit row + encrypted transcript
  F->>S: POST /text-to-speech (bulbul:v4-flash), cache miss only
  S-->>F: mp3
  F-->>A: TurnResponse: card, messages, audioUrl, locks, progress
  A->>A: render the card, speak the lines in order
  F-->>+BUS: journey.updated
  Note over A: Mic denied, cache empty or Sarvam down:<br/>captions are always on screen and<br/>the keyboard is always beside the mic
```

## The journey state machine

Code decides every transition. The LLM understands and phrases; it never moves
the journey (§9).

```mermaid
stateDiagram-v2
  [*] --> INTRO
  INTRO --> ASK_NEED
  ASK_NEED --> CONSENT_DATA
  CONSENT_DATA --> PREFILL: allowed
  CONSENT_DATA --> MANUAL_FORM: declined
  PREFILL --> CONFIRM_DETAILS
  MANUAL_FORM --> CONFIRM_DETAILS
  CONFIRM_DETAILS --> OFFERS
  OFFERS --> EXPLAIN_KFS
  EXPLAIN_KFS --> TEACHBACK
  TEACHBACK --> TEACHBACK: wrong, re-explain (3 attempts)
  TEACHBACK --> TERMS_CONSENT: all three passed
  TEACHBACK --> HUMAN_HANDOFF: still wrong after 3
  TERMS_CONSENT --> OTP
  OTP --> RECEIPT
  RECEIPT --> DONE
  DONE --> [*]
  PREFILL --> ABANDONED: idle
  OFFERS --> ABANDONED: idle
  TEACHBACK --> ABANDONED: idle
  ABANDONED --> OFFERS: rescue accepted, same step
```

`TERMS_CONSENT` is unreachable until teach-back passes, and the lock is
re-checked in the engine when the tap arrives - not only rendered as a disabled
button.

## The trust layer

```mermaid
flowchart TB
  TURN["A journey reaches RECEIPT"] --> PAYLOAD["Canonical JSON payload<br/>offer · KFS version · answers · consents"]
  PAYLOAD --> HASH["SHA-256(payload)"]
  HASH --> CHAIN["hash = SHA-256(prevHash || payloadHash || seq)"]
  CHAIN --> SIGN["Ed25519 signature<br/>key id recorded"]
  SIGN --> ROW[("receipts<br/>append-only trigger")]
  ROW --> ANCHOR["Daily Merkle root<br/>daily_anchors"]
  ROW --> VERIFY["GET /receipts/{no}/verify<br/>4 checks"]
  VERIFY --> C1["payload_hash"]
  VERIFY --> C2["chain_link"]
  VERIFY --> C3["signature"]
  VERIFY --> C4["kfs_document SHA-256"]
```

A PL/pgSQL `forbid_update_delete()` trigger runs BEFORE UPDATE OR DELETE on
`receipts`, `consents`, `audit_log` and `teachback_attempts`. Evidence the
application itself can rewrite is not evidence.

## KFS ingestion (phase 11)

```mermaid
flowchart LR
  PDF["Admin uploads a PDF"] --> CHECK["Magic bytes, 2 MB cap"]
  CHECK --> DOCAI["Sarvam Document Intelligence<br/>inline field schema"]
  DOCAI -.->|unreachable| OFFLINE["pdfplumber<br/>label/value rows"]
  DOCAI --> PARSE["parse: string -> number, or None"]
  OFFLINE --> PARSE
  PARSE --> DRAFT[("draft<br/>+ per-field confidence")]
  DRAFT --> HUMAN{"A named human<br/>verifies and corrects"}
  HUMAN --> VERIFIED[("verified")]
  VERIFIED --> GEN["sarvam-105b writes questions<br/>and lines in mr/hi/en"]
  GEN --> GUARD["Number Guard<br/>+ no digits, placeholders only"]
  GUARD --> REVIEW{"Reviewed on<br/>the dashboard"}
  REVIEW --> ACTIVE[("active<br/>offer re-priced, questions live")]
```

Nothing reaches a customer from an unverified document, and no single action
publishes model-written text.

## Why the Vite proxy

The browser only ever talks to `:5173`. Vite forwards `/api` to FastAPI, so:

- there is no CORS in development,
- the demo needs **one** HTTPS tunnel, not two,
- the frontend never hard-codes a backend host.

The iPhone does not use the proxy: it talks to the tunnel directly, which is
why the app is not subject to CORS at all and why `CORS_ORIGINS` is an
allowlist for the website only.

## Layer rules (from the build plan)

| Rule | Where it is enforced |
|---|---|
| Code decides transitions, the LLM only phrases | `app/journey/engine.py` |
| The AI never invents a number | `app/ai/number_guard.py`, and `app/kfs/questions.py` rejects any digit |
| Only the backend creates receipts | `app/trust/issue.py` + DB triggers |
| Receipts/consents/audit/attempts are append-only | `forbid_update_delete()` triggers |
| Every voice action has a tap/type alternative | `TurnResponse.quickReplies` + the keyboard toggle beside the mic |
| Ownership returns 404, never 403 | `_owned()` in `api/journeys.py`, `_owned_task()` in `api/rescue.py` |
| No PII in logs | `app/logging.py` root-logger filter |
| Admin access is allowlist-only, never client-set | `auth/users.py` + `deps.current_admin` |
| A real token always outranks the demo header | `deps.current_user`, `lib/api.ts`, `APIClient.makeRequest` |
| Demo auth is impossible in an iOS Release build | `#if DEBUG` around `DemoAuth`; verified absent from the Release binary |
| Nothing is published without human verification | `app/kfs/ingest.py` |
| No KFS document reaches a customer unverified | `kfs_documents.status` + `activate()` |
| Never deploy publicly; the concept label is always visible | `ConceptRibbon` above every screen |

## Background work

One in-process `asyncio` task, started from the FastAPI lifespan: the rescue
scheduler, ticking every 15 seconds. No broker, no worker, nothing to debug on
stage - and it dies with the backend rather than outliving it. At scale this
becomes Celery and Redis, which is recorded in `docs/SECURITY.md`.

Its database work runs in a thread (`asyncio.to_thread`) because SQLAlchemy is
synchronous here, which is also why it hands its SSE events back to the event
loop to publish rather than touching the bus from the worker (D-045).

## Ports

| Port | Service |
|---|---|
| 5173 | Vite dev server (proxies `/api`) |
| 8000 | FastAPI |
| 5433 | Postgres on the host (5432 inside the container - see DECISIONS D-004) |
| 8080 | Adminer |

## Sign-in flow

```mermaid
sequenceDiagram
  participant B as Client (app or website)
  participant FB as Firebase Auth
  participant A as FastAPI
  participant P as Postgres

  B->>FB: Google sign-in
  FB-->>B: ID token
  B->>A: GET /api/me  (Authorization: Bearer <token>)
  A->>FB: verify signature / issuer / audience / expiry
  FB-->>A: claims
  A->>P: upsert user, recompute is_admin from the allowlist
  A-->>B: {displayName, email, photoUrl, preferredLanguage, personaId, isAdmin}
```

The dev fallback replaces the first three steps with `X-Demo-User` plus
`X-Demo-Key`, which the backend honours only when `DEMO_AUTH=true`, `APP_ENV=dev`
and the key matches in constant time. A real bearer token always wins, on both
sides. In an iOS Release build the demo path does not exist in the binary.
