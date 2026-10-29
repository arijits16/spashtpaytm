# Architecture

> Phase 0 shows the shell. Boxes marked _(phase N)_ are not built yet; this file
> is updated as each phase lands.

## System

```mermaid
flowchart LR
  subgraph Phone["Phone — customer (Sunita)"]
    UI["React PWA<br/>PhoneFrame routes"]
  end

  subgraph Laptop["Laptop — lender & compliance"]
    DASH["Dashboard<br/>/dashboard/*"]
  end

  subgraph Web["Vite dev server :5173"]
    PROXY["/api proxy"]
  end

  subgraph API["FastAPI :8000"]
    HEALTH["/api/health"]
    ENGINE["Journey engine<br/>(phase 4)"]
    TRUST["Trust layer<br/>(phase 5)"]
    AI["Sarvam clients<br/>(phases 6-7)"]
  end

  DB[("PostgreSQL 16<br/>:5433 → container 5432")]
  SARVAM["Sarvam APIs<br/>Saaras · Bulbul · 105B · Doc AI"]
  FB["Firebase Auth<br/>(phase 1)"]

  UI --> PROXY
  DASH --> PROXY
  PROXY --> HEALTH & ENGINE & TRUST & AI
  ENGINE --> DB
  TRUST --> DB
  AI -.-> SARVAM
  UI -.-> FB
  API -.->|verify ID token| FB
```

## Why the Vite proxy

The browser only ever talks to `:5173`. Vite forwards `/api` to FastAPI, so:

- there is no CORS in development,
- phase 12 needs **one** HTTPS tunnel, not two,
- the frontend never hard-codes a backend host.

## Request path today (phase 0)

```mermaid
sequenceDiagram
  participant B as Browser
  participant V as Vite :5173
  participant F as FastAPI :8000
  participant P as Postgres :5433

  B->>V: GET /api/health
  V->>F: GET /api/health
  F->>P: SELECT 1
  P-->>F: ok
  F-->>V: {status, db, sarvam, version}
  V-->>B: same JSON
  Note over B: renders "Backend: OK · DB: OK"
```

## Layer rules (from the build plan)

| Rule | Where it is enforced |
|---|---|
| Code decides transitions, the LLM only phrases | `app/journey/engine.py` _(phase 4)_ |
| The AI never invents a number | `app/ai/number_guard.py` _(phase 7)_ |
| Only the backend creates receipts | `app/trust/ledger.py` + DB triggers _(phase 5)_ |
| Receipts/consents/audit/attempts are append-only | `forbid_update_delete()` triggers _(phase 2)_ |
| Every voice action has a tap/type alternative | `TurnResponse.quickReplies` + cards _(phase 4)_ |
| No PII in logs | `app/logging.py` — root-logger filter ✅ |
| Never deploy publicly; concept label always visible | `ConceptRibbon` ✅ |

## Ports

| Port | Service |
|---|---|
| 5173 | Vite dev server (proxies `/api`) |
| 8000 | FastAPI |
| 5433 | Postgres on the host (5432 inside the container — see DECISIONS D-004) |
| 8080 | Adminer |
