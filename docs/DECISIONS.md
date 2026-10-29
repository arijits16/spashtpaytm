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

### D-007 — A custom `frame` breakpoint at 500px
§5.8 puts the phone bezel at **≥ 500px**, which is not any Tailwind default
(`sm` is 640px). `--breakpoint-frame: 500px` is declared in `@theme`, and
`PhoneFrame` uses `frame:` variants. Between 500 and 640px the app is framed,
exactly as the plan specifies.

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
