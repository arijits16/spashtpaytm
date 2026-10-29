# SPASHT × Paytm — Complete Build Plan for Claude Code

**Project folder:** `spashtpaytm/` · **Team:** Finovators · **Event:** Paytm Build for India AI Hackathon – Mumbai · **Track 2:** AI-Powered Financial Journeys

> **How to use this file**
> 1. Create an empty folder `spashtpaytm/`, open it in Antigravity, and save this file as `spashtpaytm/docs/BUILD_PLAN.md`.
> 2. Start Claude Code in the `spashtpaytm/` folder and paste the **Kickoff message** from Appendix B.
> 3. Claude Code builds **one phase at a time** and stops after each phase. You test, then reply `Go Phase N`.
> 4. Things only a human can do (Firebase project, Sarvam API key, installing Docker, phone testing) are listed in Appendix D and at the top of each phase.
> 5. Before Phase 3, put the Paytm reference screenshots in `spashtpaytm/docs/reference/`. Blur your name, UPI ID and bank digits first. That folder is gitignored.
>
> **Before you start:** confirm with the organisers what you are allowed to prepare before 31 Oct (code, designs, data). Follow their rules.

---

## Table of contents

0. Instructions for Claude Code (working agreement)
1. Product brief
2. The golden demo path (must always work)
3. Tech stack (final)
4. Repository structure
5. Design system: Paytm-style concept shell (from reference screenshots)
6. Data model (PostgreSQL)
7. Mock data and language content
8. Backend API contract
9. Journey engine (state machine)
10. Sarvam AI integration (ears, brain, mouth, eyes)
11. Trust layer: the Spasht Receipt
12. Lender and compliance dashboard
13. Security, privacy and compliance rules
14. Environment variables
15. Phases 0 → 12 (the build)
16. QA checklists
17. Pitch ↔ build alignment
- Appendix A — `CLAUDE.md` (copy into repo root)
- Appendix B — Kickoff message
- Appendix C — Per-phase and fix-up messages
- Appendix D — Human setup steps
- Appendix E — Demo script

---

## 0. Instructions for Claude Code (working agreement)

You are the lead engineer building **Spasht**, a hackathon prototype that must look and behave like a production feature inside the Paytm app. Follow these rules strictly.

1. **One phase at a time.** Only do the phase the human asks for. Never start the next phase on your own.
2. **Start of each phase:** restate the goal in 3–5 lines, list the files you will create or change, and note any human action needed (keys, accounts). If a required secret is missing, stop and ask.
3. **End of each phase:** run lint and tests, start the app and check the phase's acceptance criteria, then reply with:
   - what was built (short),
   - the acceptance checklist with ✅ or ❌ for each item,
   - exact manual test steps for the human,
   - known issues,
   - then `git commit -m "phase-N: <summary>"` and **stop**.
4. **Keep the app runnable** at the end of every phase (`make dev`, or `npm run dev` on Windows, must work).
5. **Never commit secrets.** Only `.env.example` files are committed. `.env`, `backend/secrets/`, the signing keys and any Firebase service-account JSON are gitignored.
6. **The AI never invents numbers.** Every rupee amount, rate, fee and date comes from the database (KFS facts). Enforce this with the Number Guard (§10.5) and tests.
7. **Only the backend creates receipts.** The receipts, consents and audit-log tables are append-only, enforced in the database (§11).
8. **Synthetic data only.** No real personal data anywhere. Mask identifiers (Aadhaar `XXXX XXXX 4821`, mobile `+91 98•••••210`).
9. **Brand guardrails for the Paytm-style UI** (§5.1): copy the layout and feel of the reference screenshots, but do **not** copy Paytm's official logo artwork, app icon or any third-party brand logos. Show a visible "Concept demo" label. Never deploy publicly. No real payments. QR codes encode a non-payment demo string.
10. **Server-driven journey.** The backend decides the next step; the frontend renders what the backend returns (§8.2). The LLM understands and phrases; **code decides** transitions.
11. **Works without voice.** Every voice action also has a tap or typed alternative.
12. **Demo mode.** When `DEMO_MODE=true`, or when Sarvam is unreachable, the app falls back to cached audio, canned transcripts and template replies, so the demo never dies (§10.6).
13. **Code quality:** TypeScript `strict`; Python type hints; small focused modules; docstrings on core logic; no dead code; pin dependency versions; ask before adding a large new dependency.
14. **Keep docs current:** update `docs/PROGRESS.md` (phase checklist) and `docs/DECISIONS.md` (short notes on any design decision) at the end of every phase.
15. **When unsure, prefer simple and reliable over clever.** This is demoed live in a noisy hall on venue Wi-Fi.

---

## 1. Product brief

### 1.1 The problem
People in India say "yes" to loans and insurance they don't understand. The forms are long and in English, the Key Fact Statement (KFS) is a legal PDF nobody reads, and consent is a tick box. Customers either quit midway when a hidden cost surprises them, or take the product and later feel cheated. From **1 Jan 2027**, RBI's Responsible Business Conduct Directions require explicit, recorded, informed consent plus a suitability check. Proven mis-selling means a full refund plus compensation. A tick box doesn't prove anyone understood anything.

Key facts used in the product and pitch (all public):
- Fewer than 41% of borrowers felt fully informed before signing; 61% said the real cost was higher than quoted; 54% of people who quit an application did so after finding hidden fees, penalties or bundled insurance (Ken Research, 2026).
- Only 10.6% of Indians speak English (Census 2011).
- Insurance grievances on Bima Bharosa: 2.58 lakh in FY25, up 20% (IRDAI Annual Report 2024-25).

### 1.2 What Spasht does
Spasht (स्पष्ट = "clear") is a voice-first co-pilot inside the Paytm app that turns a loan application into a short conversation in the customer's own language:

1. **Bolo (Speak):** the customer talks in Marathi, Hindi or English, code-mixing welcome.
2. **Zero-form:** with consent, details come from DigiLocker, CKYC and Account Aggregator (mocked); the customer only confirms.
3. **Sahi Match:** an affordability and suitability check, and all eligible offers side by side, sorted by **true cost (APR)**, not by headline rate.
4. **Samjho (Explain):** the selected lender's KFS explained in 5 lines, red flags first, by voice and on screen.
5. **Teach-back:** 3 short questions. A wrong answer gets a simpler re-explanation. The **"I agree" button stays locked** until she understands.
6. **Consent + OTP:** separate consents (loan terms; insurance add-on defaults to **No**). The OTP is typed, never spoken.
7. **Spasht Receipt:** a hash-chained (SHA-256), Ed25519-signed record of what was explained, in which language, and how she answered. It is verifiable, and tampering is detectable.
8. **Rescue Agent (stretch):** if she gets stuck, a call-back in her language resumes at the exact step.

### 1.3 Who uses what
| User | Device | Pages |
|---|---|---|
| Customer (Sunita) | Phone (iPhone or Android browser, PWA) | Login → Paytm-style home → Spasht journey → Receipt |
| Lender / compliance team | Laptop | Dashboard: live journeys, KPIs, receipts, ledger, KFS library |
| Auditor / anyone with a receipt | Any | Public verify page `/verify/:receiptNo` |

### 1.4 Non-goals (do not build)
Real money movement, real KYC, real DigiLocker or Account Aggregator access, real telephony, public deployment, native mobile apps.

---

## 2. The golden demo path (must always work)

This exact path is the demo. Every phase must keep it working. Target length: 3–4 minutes.

1. **Phone:** open the app → "Continue with Google" → Paytm-style home screen.
2. Tap **Loan** in *Loans & Insurance* (it has a glowing `NEW · Spasht` badge), or the Spasht slide in the top banner.
3. She picks मराठी on the intro screen and Spasht greets her in Marathi. She taps the mic and says: *"मला नवीन मशीनसाठी ५०,००० चं लोन पाहिजे."*
4. **Consent card:** "Fetch your details from DigiLocker and your bank (Account Aggregator)?" Toggles default **off**; she allows both.
5. **Prefill:** about 1.5 s "fetching…", then name, DOB, address (DigiLocker), PAN and KYC (CKYC), 6-month average income ₹28,400 (Account Aggregator), EMI bank account (UPI AutoPay). She confirms shop address and mobile by saying "हो".
6. **Sahi Match:** EMI-to-income 16% ✓. Three offers side by side. Spasht says that **Partner Bank B has the lowest interest rate but costs the most after its ₹2,950 fee**, and that **Partner NBFC A is cheapest overall**. She picks A.
7. **Samjho:** the "Your loan in 5 lines" card (EMI ₹4,600 × 12, total ₹55,200, late fee ₹500 + CIBIL impact, foreclosure 4%, insurance optional, 3-day cooling-off), spoken in Marathi.
8. **Teach-back:** Q1 "What if an EMI is late?" She answers **wrong on purpose** → simpler re-explanation → correct. Q2 total repay ✓. Q3 insurance optional ✓.
9. **Consent unlocks.** The insurance add-on stays **No**. She taps "मी सहमत आहे" (I agree) → OTP sheet (demo OTP shown) → typed.
10. **Receipt:** stamp animation "SPASHT ✓ 3/3", a receipt number like `SP-7F3A9C2K`, and a mock "summary sent in Marathi" message preview.
11. **Laptop:** the journey has already appeared live on the dashboard. Open the receipt → **Verify ✓** → "Simulate tampering": change the EMI from 4600 to 4000 → **✗ TAMPERED** (hash mismatch, signature invalid).

---

## 3. Tech stack (final)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | **React + Vite + TypeScript (strict)** | One web app with phone pages and laptop pages |
| Styling | **Tailwind CSS** + CSS variables for tokens | Tokens in §5.2 |
| Motion | **Framer Motion** (or its newer package name `motion`) | Bubbles, cards, stamp |
| Routing / state | **React Router** (data-router API), **TanStack Query**, **Zustand** | Server state vs UI state |
| Icons | **lucide-react** | Line icons in Paytm-style blue |
| Fonts | `@fontsource/inter`, `@fontsource/noto-sans-devanagari` | Self-hosted; Devanagari must render everywhere |
| QR | `qrcode.react` | Encodes demo strings only |
| Charts | `recharts` | Dashboard |
| PWA | `vite-plugin-pwa` | "Add to Home Screen", standalone |
| Auth | **Firebase Authentication (Google)**, modular JS SDK | Backend verifies the ID token |
| Backend | **Python 3.11+, FastAPI, Uvicorn** | Pydantic v2, pydantic-settings; environment managed with `uv` (or venv) |
| DB | **PostgreSQL 16** (Docker locally; Supabase optional via `DATABASE_URL`) | SQLAlchemy 2 + Alembic + psycopg 3 |
| AI | **Sarvam APIs**: Saaras v4 (STT), Bulbul v4 Flash (TTS), Sarvam-105B (LLM), Sarvam Document Intelligence (KFS reading) | §10 |
| HTTP client | `httpx` (async) | Our own thin Sarvam client with timeouts and retries |
| Crypto | `hashlib` (SHA-256), **PyNaCl** (Ed25519), `cryptography` (AES-256-GCM for transcripts) | §11 |
| Live updates | **Server-Sent Events** (`sse-starlette`), read in the browser with `@microsoft/fetch-event-source` so the auth header is sent; polling fallback | Dashboard |
| Jobs | In-process background loop (FastAPI lifespan task) | Rescue Agent; Celery or Redis only "in production" |
| Firebase server | `firebase-admin` | `verify_id_token`; fallback `google-auth` `id_token.verify_firebase_token` |
| PDF | `reportlab` (generate sample KFS PDFs), `pdfplumber` (offline fallback parse) | |
| Tests | `pytest`, `pytest-asyncio`; frontend `vitest`; optional Playwright e2e | |
| Lint | `ruff`, `eslint`, `prettier` | |
| Optional | `langgraph` for the orchestrator graph; `langfuse` tracing | Only if they install and work cleanly, otherwise plain Python |

**Ports:** frontend `5173`, backend `8000`, Postgres `5432`, Adminer `8080`. The Vite dev server **proxies `/api` → `http://localhost:8000`**, so the phone needs only one HTTPS tunnel and there are no CORS issues.

**Versions:** use the current stable release of each tool at install time and pin exact versions (`package-lock.json`, and `uv.lock` or a pinned `requirements.txt`). If a major version differs from what this plan assumes (for example, Tailwind v4 defines tokens with `@theme` in CSS instead of `tailwind.config.ts`), adapt and note it in `docs/DECISIONS.md`.

---

## 4. Repository structure

```
spashtpaytm/
├── CLAUDE.md                     # rules for Claude Code (Appendix A)
├── README.md                     # setup, run, demo, architecture
├── Makefile                      # setup, dev, db-up, migrate, seed, keys, test, lint, eval, tts-cache, demo-reset, tunnel
├── package.json                  # root npm scripts with the same names (works on Windows), uses concurrently
├── .gitignore  .editorconfig
├── infra/
│   └── docker-compose.yml        # postgres:16-alpine (+ adminer)
├── docs/
│   ├── BUILD_PLAN.md             # this file
│   ├── PROGRESS.md               # phase checklist, updated every phase
│   ├── DECISIONS.md              # short design-decision log
│   ├── ARCHITECTURE.md           # diagram (mermaid) + flows
│   ├── DEMO_SCRIPT.md
│   ├── EVAL.md                   # LLM eval results (Phase 7)
│   └── reference/                # Paytm screenshots for UI matching (gitignored, personal details blurred)
├── frontend/
│   ├── index.html  vite.config.ts  tailwind.config.ts  tsconfig.json  package.json  .env.example
│   ├── public/ (pwa icons, demo audio)
│   └── src/
│       ├── main.tsx  App.tsx  routes.tsx
│       ├── styles/index.css                  # tokens as CSS vars
│       ├── lib/ api.ts firebase.ts auth.tsx i18n.ts format.ts sse.ts
│       ├── lib/audio/ recorder.ts player.ts
│       ├── components/ui/ Card Chip IconTile BottomSheet Drawer Button Badge Toast Skeleton Toggle
│       ├── components/phone/ PhoneFrame ConceptRibbon SafeArea
│       ├── features/home/ HomePage.tsx homeConfig.ts sections/*
│       ├── features/profile/ ProfileDrawer.tsx SettingsList.tsx LanguageSheet.tsx
│       ├── features/spasht/ SpashtIntro.tsx SpashtChat.tsx Stepper.tsx MicButton.tsx MessageBubble.tsx QuickReplies.tsx
│       │   ├── cards/ ConsentCard PrefillCard ConfirmCard OffersCard KfsCard QuizCard ConsentLockCard OtpSheet ReceiptCard HandoffCard ManualFormCard
│       │   └── hooks/ useJourney.ts useVoiceTurn.ts
│       ├── features/receipt/ ReceiptView.tsx VerifyPage.tsx TamperEditor.tsx LedgerChain.tsx
│       ├── features/dashboard/ DashboardLayout Overview LiveJourneys JourneyDetail Receipts Ledger KfsLibrary RescueTasks DemoControls
│       └── pages/ LoginPage.tsx NotFound.tsx
└── backend/
    ├── pyproject.toml (or requirements.txt)  .env.example  alembic.ini
    ├── alembic/versions/
    ├── app/
    │   ├── main.py  config.py  deps.py  logging.py
    │   ├── db/ base.py session.py models/*.py
    │   ├── api/ health.py me.py journeys.py voice.py receipts.py ledger.py dashboard.py admin.py kfs.py rescue.py
    │   ├── auth/ firebase.py demo.py
    │   ├── journey/ states.py engine.py context.py understand_rules.py suitability.py offers.py teachback.py loan_math.py responses.py
    │   ├── journey/templates/ mr-IN.json hi-IN.json en-IN.json
    │   ├── adapters/ base.py digilocker_mock.py ckyc_mock.py aa_mock.py upi_autopay_mock.py
    │   ├── ai/ sarvam_client.py stt.py tts.py llm.py understand_llm.py explain.py grade.py reexplain.py number_guard.py speakable.py docai.py
    │   ├── ai/prompts/ system.md understand.md grade.md reexplain.md kfs_questions.md
    │   ├── trust/ canonical.py ledger.py signing.py verify.py merkle.py crypto_box.py
    │   ├── events/ bus.py
    │   ├── rescue/ scheduler.py
    │   ├── seed/ data/*.json run.py
    │   └── assets/kfs/*.pdf
    ├── scripts/ generate_kfs_pdf.py gen_keys.py tts_cache.py
    ├── secrets/            # gitignored: ed25519 keys, transcript key, optional firebase service account
    ├── .cache/tts/         # gitignored: cached audio
    ├── evals/ utterances.jsonl run_eval.py
    └── tests/
```

---

## 5. Design system: Paytm-style concept shell

The reference screenshots show the current Paytm iOS app: the home screen (top and scrolled), the profile and QR drawer with the settings list, the profile-completion page, and the "screenshots blocked" screen on sensitive pages. Rebuild that **look and layout**, then add Spasht as the one working feature.

### 5.1 Brand and legal guardrails (mandatory)
- Header wordmark: plain text **"Paytm"** in the navy colour, a standard bold font, followed by a small `Concept` pill. **Do not recreate the official two-tone logo artwork or the app icon.** If the organisers provide official brand assets for the hackathon, the team may drop them into `public/brand/` later.
- A small persistent **concept ribbon** at the very top: `Concept demo · Paytm Build for India AI Hackathon · not the live Paytm app`.
- "Promoted" partner tiles use generic placeholders (coloured circles with initials, like "Partner Life A"). **No real bank or insurer logos.**
- All non-Spasht tiles open a bottom sheet: "This is a concept demo. Only **Spasht** is live in this prototype." with a `Try Spasht →` button.
- QR codes encode `SPASHT-CONCEPT-DEMO-<random>`, never a `upi://` URL.
- Never deploy to a public URL. Use localhost or a temporary tunnel only during the demo (Appendix D).
- The screenshots in `docs/reference/` are only for matching the look. Keep them out of git, and never copy personal details from them into code, seed data or tests.

### 5.2 Tokens
Put these in `src/styles/index.css` as CSS variables and map them in `tailwind.config.ts`.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F3F4F6` | App background (light grey) |
| `--card` | `#FFFFFF` | Section cards |
| `--navy` | `#002E6E` | Wordmark, primary buttons, user bubbles |
| `--navy-icon` | `#0F3D86` | Filled circles behind UPI icons |
| `--navy-grad` | `linear-gradient(180deg,#1A4FA6 0%,#0B3A82 100%)` | Floating "Scan QR" pill |
| `--sky` | `#00BAF2` | Accents, QR border top half, progress |
| `--link` | `#1F6FEB` | "View All →" links |
| `--icon-line` | `#1D5BD0` | Outline icons (stroke 1.75) |
| `--text-1` | `#1C1C1E` | Titles |
| `--text-2` | `#3A3A3C` | Labels |
| `--text-3` | `#6B7280` | Secondary text |
| `--offer-strip` | `#D6F1FA` | "Exclusive offer" strip |
| `--promo-red` | `#D32F2F` | Festive promo text in the top bar |
| `--badge-new` | `#FFE14D` | "New" badges (dark text) |
| `--alert-pink` | `#FDECEC` | Pink alert strip in the profile card |
| `--success` | `#12B76A` | Verified, passed |
| `--danger` | `#D92D20` | Red flags, tampered |
| `--warning` | `#F79009` | "Lowest rate but high fees" |
| Profile cards | `#1565E5`, `#0B6B4F`, `#B0275A`, `#1E3A7A` | Blue, green, raspberry, navy tiles |

**Type:** Inter for Latin text and Noto Sans Devanagari for Devanagari (set as a font-family fallback chain). Section title 20/26 bold; tile label 13/16 medium (two lines, centred); chip 13/16; body 15/22; caption 12/16.
**Shape:** cards radius 20px, banners 16px, pills fully rounded, icon circles 56px.
**Spacing:** screen side padding 14px, 12px gap between cards, 18px card padding.
**Elevation:** cards are flat on the grey background (no shadow). The floating Scan QR pill has `0 8px 24px rgba(0,46,110,.35)`.

### 5.3 Home screen anatomy (top to bottom)
Everything is data-driven from `features/home/homeConfig.ts`, so content can be edited without touching components.

1. **Top bar (56px):** avatar circle (44px, initials of the Google user on a `#D9E8C4` background, or their photo). Two-line promo text: red line "Festive offers on bills*" and a bold black line "with 20% Cashback*" with a small blue circular chevron. Search and bell icons on the right.
2. **Promo carousel** (height ~180px, radius 16px, auto-advance every 4s, dots below):
   - Slide 1 (**Spasht**): navy-to-sky gradient, title "Loan, ab aapki bhasha mein", subtitle "Bolo · Samjho · Spasht", white pill CTA `Try Spasht →`, and a CSS mic illustration with pulsing rings. Opens `/spasht`.
   - Slide 2: warm cream and gold gradient, "Pay your household bills · Earn reward coins", navy `Pay Now →` pill (non-functional).
   - Slide 3: "Cashback on recharges", generic.
3. **UPI Money Transfer** card: 4 tiles with white icons on navy circles: Scan any QR, Pay Anyone, To Bank & Self A/c, Balance & History.
4. **Recharge & Bills** card: title plus `View All →`; a horizontally scrolling row of outline-icon tiles: Mobile Recharge, Credit Card Bill, Electricity Bill, FASTag Recharge, Loan EMI Payment, DTH, Gas; small scroll-indicator pill.
5. **Exclusive offer strip** (cyan, rounded): gift icon, "Exclusive offer for You!" / "Claim your exclusive reward", chevron.
6. **Two-column grid:** a tall left card "Paytm Postpaid — Start using with up to ₹1 Lakh limit"; right column "Refer & Win" and "Save in Gold" cards.
7. **Chips row** (horizontal scroll): Refer & Win ₹400 · Cashback & Offers · UPI Lite.
8. **Travel & Tickets:** Flight, Train, Bus, Hotels; chips "₹1200* OFF on Flights", "15% Off* on Bus".
9. **Grow Your Money:** Save in Gold, Save in Silver, Mutual Fund (yellow badge "SIP @ ₹21"), Apply for IPOs.
10. ★ **Loans & Insurance:** **Loan** (Spasht-enabled: yellow `NEW` badge, small navy ribbon "Spasht · मराठी / हिंदी", soft pulsing sky ring), Paytm Postpaid, Car Insurance, Health Insurance (red heart icon); chips "Get Credit Card", "Bike Insurance". Loan opens `/spasht?product=personal_loan`.
11. **Free Tools:** horizontally scrolling coloured cards (about 130×150): "Check Your Credit Score" (mint, SVG gauge with a placeholder score such as 750), "Round Up Spends In Gold" (cream), "Track Your Spends" (pink, a mini list of made-up amounts such as ₹1,250 · ₹3,480 · ₹860).
12. **Do More with Paytm:** Claim Deals, Gift Vouchers, Cashback & Offers, See All Services; chips "App Store | 4% Off", "Deals Near You | 50% OFF".
13. **Promoted:** 4 generic partner placeholders (§5.1).
14. **Referral card:** "You ❤ Paytm — Your referral streak unlocks Assured ₹400 →" with a CSS gift graphic; small "T&C apply".
15. **Floating "Scan QR" pill** fixed at the bottom centre (about 220×60, navy gradient, white bold text, QR icon, light-blue 2px border). Opens the "concept demo" sheet.
16. **First-visit tooltip** (once, stored in localStorage): "New: loans in Marathi & Hindi →", pointing at the Loan tile.

### 5.4 Profile drawer (tap the avatar)
A drawer slides in from the left covering ~90% of the width, over a dimmed backdrop.
- Header: back arrow, wordmark centred.
- Profile card: avatar with a thin gradient ring and a small camera badge; Google display name with a blue verified tick; `UPI ID: demo-xxxx@ptdemo` (synthetic) with a copy icon. Pink alert strip: red ⓘ "Receive money on Paytm from all UPI apps" with a navy `Enable now` pill (non-functional).
- Tapping the profile card opens a non-functional **Profile completion** page: avatar, name, a 0% progress bar, and four coloured cards (Personal info in blue, Financial preferences in green, Lifestyle preferences in raspberry, Other preferences in navy), each with a time estimate and a 0% ring. Its data-sharing consent checkbox at the bottom starts **unticked**.
- QR card: large QR (§5.1) inside a rounded frame whose **top half border is sky and bottom half is navy**.
- Bank row: "Demo Bank – 1234 · Change Bank". Two pill buttons: `Share QR`, `Download`.
- **Settings** card with search icon. Rows with outline icon, title, subtitle and chevron: Pocket Money (yellow `New` badge), UPI & Payment Settings, Automatic Payments, Orders & Bookings, **Profile — Privacy, Notification & Language** (*functional:* opens the language sheet mr / hi / en and saves `preferred_language`), Refer & Win, Help & Support, MyUPI, Appearance.
- "Security Shield — Protect your account" row with an `Activate` pill.
- Footer: wordmark text, "Crafted & Owned by India" with a thin tricolour line, policy links, and **Logout**.

### 5.5 Login and splash
- Background: light-blue vertical gradient (`#E6F6FD → #FFFFFF → #E6F6FD`), similar to Paytm's blocked-screen look. Centred text wordmark plus `Concept` pill, tagline "Spasht · loans you understand".
- `Continue with Google` button (follow Google's sign-in button guidelines), and `Continue as demo user` (shown only when `VITE_DEMO_AUTH=true`).
- Footer: "Concept prototype for Paytm Build for India AI Hackathon · not the live Paytm app".

### 5.6 Spasht journey UI (`/spasht`)
- **Header:** back arrow; title "Spasht" with a small "in Paytm (concept)" caption; language pill (`मराठी ▾`); step **progress bar** with 6 labelled steps: *Bolo · Details · Offers · Samjho · Check · Done*, plus "≈ 2 min left".
- **Conversation area:** assistant bubbles on the left (white, 1px `#E5E7EB` border, small speaker button to replay audio) and user bubbles on the right (navy, white text). States: `Listening…` with a live waveform, `Thinking…` (3 dots), `Speaking…` (animated speaker). Captions always visible.
- **Inline cards** (server-driven, §8.2):
  - `ConsentCard`: one toggle per purpose (DigiLocker, Account Aggregator), **default off**, an `Allow` button, a "Not now" link (opens `ManualFormCard`), and a one-line "why we need this".
  - `PrefillCard`: rows with a green check and a source tag (DigiLocker / CKYC / Account Aggregator / UPI AutoPay), staggered fade-in.
  - `ConfirmCard`: 2 editable fields (shop address, mobile) with `Haan / Edit`.
  - `OffersCard`: 3 offer cards stacked (or swipeable). Each shows lender, interest rate, processing fee, **APR (bold)**, EMI, total repay, total cost of credit, and a `View KFS` link. Badges: `Lowest total cost` (green) and `Lowest rate, but high fees` (amber). Sorted by APR.
  - `KfsCard`: "Your loan in 5 lines", with red-flag lines in red, a `SAMPLE TERMS` tag, and a "Read full KFS (PDF)" link.
  - `QuizCard`: question, 2–3 option buttons, a mic to answer by voice, correct/incorrect feedback states, "Question 1 of 3".
  - `ConsentLockCard`: lock icon; `मी सहमत आहे / I agree` **disabled until teach-back passes**; a separate insurance add-on toggle **default off**; each consent shows exactly what you are agreeing to.
  - `OtpSheet`: bottom sheet with 6 boxes, typed only; when `OTP_DEMO=true` a toast shows the generated code (for example "Demo OTP: 482913").
  - `ReceiptCard`: stamp "SPASHT ✓ 3/3" (green outline, rotated −6°, spring animation), receipt number, key facts, QR to the verify page, a mock chat-message preview "Summary sent in Marathi" (generic bubble, no third-party logo), `Back to Paytm`.
  - `HandoffCard`: "A Paytm loan expert will call you (9 am – 6 pm)".
- **Bottom bar:** large mic button (72px navy circle, white mic, press-and-hold **or** tap to toggle, pulsing rings while recording), keyboard toggle for typing, and quick-reply chips from the backend (e.g., `हो`, `समजलं नाही`, `पुन्हा सांगा`, `माणसाशी बोलायचं`).
- Motion: bubbles slide up and fade (150 ms), cards expand, gentle confetti on the receipt (one burst).

### 5.7 Dashboard UI (`/dashboard`, laptop)
Left sidebar (dark navy `#0B1F44`) with Overview, Live journeys, Receipts, Ledger, KFS library, Rescue tasks, Demo controls. White content area with Inter font, cards, tables and Recharts charts (details in §12).

### 5.8 Responsive rules
- Phone routes (`/`, `/login`, `/spasht`, `/spasht/rescue/:taskId`, `/receipt/:no`): on screens ≥ 500px wide, render inside a centred **PhoneFrame** (390×844, radius 44, dark bezel, fake status bar). On real phones, render full-screen with safe-area insets (iOS standalone).
- Laptop routes (`/dashboard/*`): desktop layout, minimum width 1100px.
- `/verify/:receiptNo` is responsive (works on both).

### 5.9 Sound
Short earcons (generated tones, no copyrighted sounds) for start listening, stop and success. Mute toggle in the header.

---

## 6. Data model (PostgreSQL)

Implement with SQLAlchemy 2 models and an Alembic migration. Use `uuid` primary keys unless noted and `timestamptz` for times. Use UTC in storage and display in IST.

```text
users(id, firebase_uid UNIQUE, email, display_name, photo_url, preferred_language DEFAULT 'mr-IN',
      persona_id → personas.id, is_admin BOOL DEFAULT false, created_at, updated_at)

personas(id TEXT PK e.g. 'sunita', full_name, display_name_masked, name_local JSONB {mr,hi}, gender, age, dob DATE, city, locality,
         occupation, business_name, language, mobile_masked, consent_callbacks BOOL, dnd BOOL)

digilocker_records(id, persona_id, doc_type ['aadhaar','pan','address_proof'], data JSONB, issuer)
ckyc_records(id, persona_id, ckyc_number_masked, kyc_status, last_updated DATE, data JSONB)
aa_statements(id, persona_id, fip_name, account_masked, month DATE, total_credits NUMERIC, total_debits NUMERIC,
              avg_balance NUMERIC, bounce_count INT, existing_emi NUMERIC)

lenders(id TEXT PK, name, type ['NBFC','Bank'], reg_no_sample, grievance_contact_sample)
loan_offers(id TEXT PK, lender_id, product 'personal_loan', principal, tenure_months, rate_pa, rate_type 'reducing',
            processing_fee, gst_on_fee, emi, total_repay, total_interest, apr, late_fee, foreclosure_pct,
            cooling_off_days, insurance_optional BOOL DEFAULT true, insurance_premium, kfs_document_id, active)
kfs_documents(id, lender_id, offer_id, version, file_path, file_sha256, facts JSONB, verified_by, verified_at,
              source ['seed','sarvam_docai'], status ['draft','verified','active','retired'], created_at)
kfs_clauses(id, kfs_document_id, clause_key, title, text_en, tsv TSVECTOR)   -- Postgres full-text search

teachback_questions(id TEXT PK, kfs_fact_key, sort_order, prompt JSONB{mr,hi,en}, options JSONB[{id,text{mr,hi,en},correct}],
                    reexplain JSONB{mr,hi,en}, rubric JSONB{mr:[...],hi:[...],en:[...]}, active)

journeys(id, user_id, persona_id, product, language, step, status ['active','completed','abandoned','needs_human'],
         context JSONB, selected_offer_id, kfs_document_id, version INT (optimistic lock),
         started_at, updated_at, last_activity_at, completed_at)
conversation_turns(id BIGSERIAL, journey_id, turn_no, role ['user','assistant'], text_enc BYTEA, nonce BYTEA,
                   language, source ['voice','text','tap'], stt_ms, llm_ms, tts_ms, created_at)
teachback_attempts(id BIGSERIAL, journey_id, question_id, attempt_no, answer_type ['option','voice','text'],
                   answer_value, is_correct, grader ['rule','llm'], confidence, created_at)          -- append-only
consents(id BIGSERIAL, journey_id, purpose ['fetch_digilocker','fetch_account_aggregator','loan_terms',
         'insurance_addon','callback'], granted BOOL, default_value BOOL DEFAULT false,
         method ['tap','voice','tap+otp'], evidence JSONB, created_at)                               -- append-only
otp_challenges(id, journey_id, code_hash, expires_at, attempts, verified_at)

receipts(id, receipt_no UNIQUE, seq BIGINT UNIQUE, journey_id UNIQUE, payload JSONB, payload_canonical TEXT,
         prev_hash CHAR(64), hash CHAR(64) UNIQUE, signature TEXT, signing_key_id, created_at)        -- append-only
ledger_head(id INT PK CHECK (id=1), last_seq BIGINT, last_hash CHAR(64))                              -- serialises appends
signing_keys(key_id TEXT PK, public_key_b64, active BOOL, created_at)
daily_anchors(day DATE PK, merkle_root CHAR(64), receipt_count INT, created_at)

audit_log(id BIGSERIAL, journey_id NULL, actor ['customer','system','agent','admin'], event_type, step,
          data JSONB, created_at)                                                                     -- append-only
rescue_tasks(id, journey_id, kind ['stuck','human'], reason, step, status ['pending','ringing','resumed','closed'],
             contact_window_ok BOOL, created_at, updated_at)
```

**Append-only enforcement (in the migration):**
- A PL/pgSQL function `forbid_update_delete()` that raises an exception, attached as `BEFORE UPDATE OR DELETE` row triggers on `receipts`, `consents`, `audit_log` and `teachback_attempts`.
- Document in `DECISIONS.md` that in production the app's DB role would only have `INSERT, SELECT` on these tables, and that `TRUNCATE` is used only by the dev-only `make demo-reset`.

**Indexes:** `journeys(status, last_activity_at)`, `audit_log(journey_id, created_at)`, `receipts(created_at)`, the GIN index on `kfs_clauses.tsv`.

---

## 7. Mock data and language content

Put seed files in `backend/app/seed/data/*.json` and load them with an **idempotent** `make seed`. All data is synthetic.

### 7.1 Personas
| id | Name (masked) | Profile | Language | 6-month avg income (AA) | Existing EMI |
|---|---|---|---|---|---|
| `sunita` (default) | Sunita J. | 34, F, tailor ("Jadhav Tailors"), Ghatkopar West, Mumbai 400086 | mr-IN | ₹28,400 (monthly credits 27,500 · 29,800 · 26,400 · 31,200 · 27,600 · 27,900) | ₹0 |
| `ramesh` | Ramesh Y. | 42, M, auto-rickshaw driver, Kurla | hi-IN | ₹22,000 | ₹3,000 |
| `priya` | Priya N. | 28, F, BPO executive, Thane | en-IN | ₹38,000 | ₹0 |

Identifiers are fake but format-correct: Aadhaar `XXXX XXXX 4821`, PAN `ABCPJ1234F`, CKYC `XXXXXXXXXX1234`, mobile `+91 98•••••210`. Each new Google user is linked to `sunita` by default; admins can switch persona from Demo controls.

### 7.2 Offers and KFS facts (exact numbers; tests must assert them)
Principal ₹50,000, tenure 12 months, reducing-balance EMI. APR = 12 × the monthly IRR of the cash flows: the **net amount received** (principal minus fee and GST), then 12 EMIs. This convention produces the numbers below; record it in `DECISIONS.md`.

| Offer | Lender (fictional) | Rate p.a. | Processing fee + GST | EMI | Total repay | Total cost of credit | APR | Late fee | Foreclosure | Cooling-off |
|---|---|---|---|---|---|---|---|---|---|---|
| `offer_a` | Partner NBFC A | 18.67% | ₹0 | **₹4,600** | ₹55,200 | ₹5,200 | **18.67%** | ₹500 per missed EMI | 4% of outstanding | 3 days |
| `offer_b` | Partner Bank B | 15.99% | ₹2,500 + ₹450 = ₹2,950 | ₹4,536 | ₹54,432 | ₹7,382 | **≈ 27.80%** | ₹600 | 3% | 3 days |
| `offer_c` | Partner NBFC C | 21.00% | ₹0 | ₹4,656 | ₹55,872 | ₹5,872 | **21.01%** | ₹450 | 5% | 3 days |

- Optional credit-life insurance add-on: ₹750 one-time, **default No**, never pre-selected.
- `loan_math.py` provides `emi()`, `apr_irr()`, `total_cost()`. Unit tests assert the table above (EMI to the nearest rupee, APR within ±0.05%).
- **The demo insight:** Bank B has the lowest interest rate but the highest true cost. Spasht says so plainly.
- `scripts/generate_kfs_pdf.py` (reportlab) creates `partner_nbfc_a_kfs_v3_2.pdf` (and B, C). These are realistic 2-page English KFS documents in the RBI format (APR, fees, charges, cooling-off, grievance officer, all sample), each watermarked `SAMPLE`. Store each file's SHA-256 in `kfs_documents.file_sha256`, and split the clauses into `kfs_clauses`.

### 7.3 Teach-back question bank (seed exactly; a native speaker on the team should review)
Placeholders like `{LATE_FEE}` are filled from the KFS facts by code.

**Q1 `q_late_fee`** (fact: `late_fee`)
- mr: "EMI उशिरा भरला तर काय होईल?" · options: ✅ "₹{LATE_FEE} लेट फी लागेल आणि CIBIL स्कोर कमी होऊ शकतो" / "काही होणार नाही" / "कर्ज रद्द होईल"
- hi: "अगर EMI देर से भरी, तो क्या होगा?" · ✅ "₹{LATE_FEE} लेट फीस लगेगी और CIBIL स्कोर गिर सकता है" / "कुछ नहीं होगा" / "लोन रद्द हो जाएगा"
- en: "If you pay an EMI late, what happens?" · ✅ "A ₹{LATE_FEE} late fee, and my CIBIL score can drop" / "Nothing happens" / "The loan gets cancelled"
- Re-explain mr: "समजा, तुम्ही EMI ठरलेल्या तारखेनंतर भरला, तर ₹{LATE_FEE} दंड लागेल आणि तुमचा CIBIL स्कोर खाली जाईल. पुढे कर्ज मिळायला अडचण येऊ शकते."
- Re-explain hi: "मान लीजिए आपने EMI तय तारीख के बाद भरी, तो ₹{LATE_FEE} जुर्माना लगेगा और आपका CIBIL स्कोर गिरेगा। आगे लोन मिलने में मुश्किल हो सकती है।"
- Re-explain en: "Say you pay the EMI after the due date. You pay a ₹{LATE_FEE} fine and your CIBIL score falls, which makes future loans harder."
- Rubric keywords: mr [लेट फी, दंड, CIBIL, सिबिल, स्कोर, कमी]; hi [लेट फीस, जुर्माना, CIBIL, सिबिल, स्कोर, गिर]; en [late fee, fine, penalty, CIBIL, credit score, drop]

**Q2 `q_total_repay`** (facts: `total_repay`, `emi`, `tenure_months`)
- mr: "{TENURE} महिन्यांत एकूण किती पैसे परत करावे लागतील?" · ✅ "₹{TOTAL_REPAY}" / "₹{PRINCIPAL}" / "₹{EMI}"
- hi: "{TENURE} महीनों में कुल कितना चुकाना होगा?" · same options
- en: "In total, how much will you repay over {TENURE} months?" · same options
- Re-explain mr: "दर महिन्याला ₹{EMI}, असे {TENURE} महिने, म्हणजे एकूण ₹{TOTAL_REPAY}. यात ₹{TOTAL_INTEREST} व्याज आहे."
- Re-explain hi: "हर महीने ₹{EMI}, ऐसे {TENURE} महीने, यानी कुल ₹{TOTAL_REPAY}। इसमें ₹{TOTAL_INTEREST} ब्याज है।"
- Re-explain en: "₹{EMI} every month for {TENURE} months makes ₹{TOTAL_REPAY} in total. That includes ₹{TOTAL_INTEREST} of interest."

**Q3 `q_insurance_optional`** (fact: `insurance_optional`)
- mr: "कर्जासोबत विमा घेणे बंधनकारक आहे का?" · ✅ "नाही, विमा ऐच्छिक आहे. नाही म्हणता येतं" / "हो, बंधनकारक आहे"
- hi: "क्या लोन के साथ बीमा लेना ज़रूरी है?" · ✅ "नहीं, यह ज़रूरी नहीं है, मना कर सकते हैं" / "हाँ, ज़रूरी है"
- en: "Is the insurance with this loan compulsory?" · ✅ "No, it is optional. I can say no" / "Yes, it is compulsory"
- Re-explain mr: "विमा घ्यायचा की नाही हे पूर्णपणे तुमच्या हातात आहे. विमा न घेताही तुमचं कर्ज मंजूर होऊ शकतं."
- Re-explain hi: "बीमा लेना या न लेना पूरी तरह आपकी मर्ज़ी है। बीमा न लेने पर भी आपका लोन मंज़ूर हो सकता है।"
- Re-explain en: "Taking insurance is completely your choice. Your loan can be approved even if you say no."

**Spare Q4 `q_cooling_off`** (fact: `cooling_off_days`)
- mr: "{COOLING_OFF_DAYS} दिवसांत तुमचा विचार बदलला, तर काय करू शकता?" · ✅ "मुद्दल आणि तेवढ्या दिवसांचं व्याज परत करून दंडाशिवाय कर्ज बंद करू शकता" / "काहीच करू शकत नाही" / "मोठा दंड भरावा लागेल"
- hi: "अगर {COOLING_OFF_DAYS} दिन के अंदर मन बदल जाए, तो क्या कर सकते हैं?" · ✅ "मूल रकम और उतने दिनों का ब्याज लौटाकर बिना जुर्माने के लोन बंद कर सकते हैं" / "कुछ नहीं कर सकते" / "भारी जुर्माना देना होगा"
- en: "If you change your mind within {COOLING_OFF_DAYS} days, what can you do?" · ✅ "Repay the principal plus interest for those days and exit with no penalty" / "Nothing" / "Pay a big penalty"

### 7.4 Speech templates (`journey/templates/<lang>.json`)
Keep spoken replies to 2–3 short sentences; the card carries the detail. The assistant persona speaks in the first person feminine in Marathi and Hindi (it uses a female voice).

| Key | mr-IN | hi-IN | en-IN |
|---|---|---|---|
| `greet` | नमस्कार! मी स्पष्ट. तुम्हाला किती रकमेचं आणि कशासाठी कर्ज हवं आहे? | नमस्ते! मैं स्पष्ट हूँ। आपको कितने का और किस लिए लोन चाहिए? | Hi! I'm Spasht. How much do you need, and what for? |
| `ask_consent` | तुमची माहिती आपोआप भरण्यासाठी DigiLocker आणि तुमच्या बँकेकडून माहिती घेऊ का? नाही म्हटलं तरी चालेल. | क्या आपकी जानकारी अपने-आप भरने के लिए DigiLocker और आपके बैंक से जानकारी ले लूँ? आप मना भी कर सकते हैं। | May I fetch your details from DigiLocker and your bank to fill the form? You can say no. |
| `prefilled` | तुमची माहिती भरली आहे. फक्त दुकानाचा पत्ता आणि मोबाईल नंबर कन्फर्म करा. | आपकी जानकारी भर दी है। बस दुकान का पता और मोबाइल नंबर कन्फर्म कीजिए। | Your details are filled in. Just confirm your shop address and mobile number. |
| `offers` | तुमच्यासाठी {OFFER_COUNT} ऑफर आहेत. सगळ्यात कमी व्याजदर म्हणजे सगळ्यात स्वस्त नाही. शुल्क धरून {BEST_LENDER} सगळ्यात स्वस्त आहे. | आपके लिए {OFFER_COUNT} ऑफर हैं। सबसे कम ब्याज दर का मतलब सबसे सस्ता नहीं। फीस मिलाकर {BEST_LENDER} सबसे सस्ता है। | You have {OFFER_COUNT} offers. The lowest interest rate isn't the cheapest. After fees, {BEST_LENDER} costs the least. |
| `explain_1` | तुमचा EMI दर महिन्याला ₹{EMI}, {TENURE} महिने. एकूण परतफेड ₹{TOTAL_REPAY}. | आपकी EMI हर महीने ₹{EMI}, {TENURE} महीने। कुल चुकाना ₹{TOTAL_REPAY}। | Your EMI is ₹{EMI} a month for {TENURE} months. You repay ₹{TOTAL_REPAY} in total. |
| `explain_2` | EMI उशिरा भरला तर ₹{LATE_FEE} दंड लागेल आणि CIBIL स्कोर कमी होऊ शकतो. विमा ऐच्छिक आहे, तुम्ही नाही म्हणू शकता. | EMI देर से भरी तो ₹{LATE_FEE} लेट फीस लगेगी और CIBIL स्कोर गिर सकता है। बीमा वैकल्पिक है, आप मना कर सकते हैं। | A late EMI costs ₹{LATE_FEE} and can lower your CIBIL score. Insurance is optional, and you can say no. |
| `explain_3` | मुदतीआधी कर्ज बंद केलं तर बाकी रकमेवर {FORECLOSURE_PCT}% शुल्क लागेल. विचार बदलला तर {COOLING_OFF_DAYS} दिवसांत दंडाशिवाय कर्ज बंद करता येईल. | समय से पहले लोन बंद किया तो बाकी रकम पर {FORECLOSURE_PCT}% चार्ज लगेगा। मन बदल जाए तो {COOLING_OFF_DAYS} दिन के अंदर बिना जुर्माने के लोन बंद कर सकते हैं। | Closing the loan early costs {FORECLOSURE_PCT}% of what is left. If you change your mind, you can exit within {COOLING_OFF_DAYS} days with no penalty. |
| `quiz_intro` | आता ३ छोटे प्रश्न, तुम्हाला सगळं नीट समजलं का हे बघण्यासाठी. | अब 3 छोटे सवाल, यह देखने के लिए कि सब ठीक से समझ आया या नहीं। | Now 3 quick questions, to make sure everything is clear. |
| `correct` | एकदम बरोबर! | बिल्कुल सही! | Exactly right! |
| `wrong` | जवळजवळ! मी सोप्या शब्दांत सांगते. | लगभग! मैं आसान शब्दों में बताती हूँ। | Almost! Let me put it more simply. |
| `unlocked` | छान! आता "मी सहमत आहे" बटण सुरू झालं आहे. विम्याचा पर्याय वेगळा आहे आणि तो "नाही" वर आहे. | बढ़िया! अब "मैं सहमत हूँ" बटन चालू हो गया है। बीमा का विकल्प अलग है और "नहीं" पर है। | Great! The "I agree" button is now unlocked. Insurance is a separate choice, set to "No". |
| `otp` | पुष्टीसाठी तुमच्या मोबाईलवर आलेला OTP टाइप करा. तो कधीच बोलून सांगू नका. | पुष्टि के लिए अपने मोबाइल पर आया OTP टाइप कीजिए। इसे कभी बोलकर न बताएँ। | Type the OTP sent to your phone to confirm. Never say it out loud. |
| `done` | झालं! तुमची स्पष्ट पावती तयार आहे आणि मराठीत सारांश पाठवला आहे. | हो गया! आपकी स्पष्ट रसीद तैयार है और हिंदी में सारांश भेज दिया है। | Done! Your Spasht receipt is ready and a summary has been sent to you. |
| `handoff` | काही हरकत नाही. आमचे कर्ज तज्ज्ञ सकाळी ९ ते संध्याकाळी ६ दरम्यान तुम्हाला फोन करतील. | कोई बात नहीं। हमारे लोन एक्सपर्ट सुबह 9 से शाम 6 के बीच आपको कॉल करेंगे। | No problem. A loan expert will call you between 9 am and 6 pm. |
| `rescue_call` | नमस्कार {NAME_HONORIFIC}, तुमचा कर्ज अर्ज अर्धवट राहिला आहे. जिथे थांबलात तिथूनच पुढे सुरू करूया का? | नमस्ते {NAME_HONORIFIC}, आपका लोन आवेदन अधूरा रह गया है। जहाँ रुके थे, वहीं से आगे बढ़ें? | Hi {NAME_HONORIFIC}, your loan application is incomplete. Shall we continue where you stopped? |
| `didnt_catch` | माफ करा, मला नीट ऐकू आलं नाही. पुन्हा सांगाल का? | माफ़ कीजिए, ठीक से सुनाई नहीं दिया। फिर से बताएँगे? | Sorry, I didn't catch that. Could you say it again? |

`{NAME_HONORIFIC}` is built by code from `personas.name_local` and gender: mr "सुनीता ताई" / "रमेश दादा", hi "सुनीता जी", en "Sunita". Static template lines (for example "९ ते ६" in `handoff`) are pre-approved; the Number Guard (§10.5) checks LLM-generated text.

### 7.5 Rule-based understanding lexicon (`understand_rules.py`)
- **Yes:** mr हो, होय, हां, चालेल, ठीक आहे, बरोबर, ho, hoy · hi हाँ, हां, जी, ठीक है, सही, haan, ji · en yes, yeah, ok, okay, sure, correct
- **No:** mr नाही, नको, nahi, nako · hi नहीं, ना, मत, nahi, na · en no, nope, don't
- **Didn't understand:** mr समजलं नाही, समजले नाही, कळलं नाही, पुन्हा सांगा · hi समझ नहीं आया, फिर से बताओ, दोबारा · en didn't understand, repeat, again, what
- **Human:** mr माणसाशी बोलायचं, एजंट · hi इंसान से बात, एजेंट · en human, agent, person
- **Amounts:** "50 हजार", "५०,०००", "पन्नास हजार", "पचास हज़ार", "fifty thousand", "50k", "50,000"; convert Devanagari digits ०–९ and handle हजार/हज़ार/hazaar/thousand and लाख/lakh multipliers.
- **Offer choice:** "पहिला/पहली/first/A", "NBFC A", lender names, "सगळ्यात स्वस्त / सबसे सस्ता / cheapest" → lowest APR.

---

## 8. Backend API contract

All routes are under `/api`. Protected routes need `Authorization: Bearer <Firebase ID token>`; in `DEMO_AUTH` mode, `X-Demo-User: <persona_id>` is accepted instead.

### 8.1 Routes
| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health` | public | `{status, db, sarvam: "configured" \| "demo", version}` |
| `GET /me` · `PATCH /me` | user | Profile; update `preferred_language` |
| `POST /me/persona` | admin/dev | Switch the linked persona |
| `POST /journeys` | user | Start a journey `{product, language}` → `TurnResponse` (greeting) |
| `GET /journeys/{id}` | owner | Current state and last `TurnResponse` (resume) |
| `POST /journeys/{id}/turn` | owner | **Single entry for text and taps**: `{input: {type: "text" \| "tap", value?, action?}}` → `TurnResponse` |
| `POST /voice/turn` | owner | Multipart `{journey_id, audio, language_hint?}` → STT → engine → TTS → `TurnResponse` (with transcript and audio) |
| `GET /audio/{key}.mp3` | public (unguessable key) | Serve cached TTS audio. Keys are HMAC values (§10.2), so `<audio>` can play them without an auth header |
| `GET /kfs/{document_id}/file` | user | Serve the sample KFS PDF ("Read full KFS" link) |
| `POST /journeys/{id}/otp/send` | owner | `{sent: true, demo_code?}` (`demo_code` only when `OTP_DEMO=true`) |
| `POST /journeys/{id}/otp/verify` | owner | `{code}` → `TurnResponse` with the receipt card |
| `GET /receipts/{no}` | public / owner / admin | Public: a minimal view (lender, product, language, teach-back score, time, hashes). Owner or admin: the full masked payload |
| `GET /receipts/{no}/verify` | public | `{valid, checks: [{name, ok, detail}], hash, prev_hash, seq, key_id}` |
| `POST /receipts/{no}/verify-candidate` | owner / admin | Verify an **edited copy** of the payload (tamper demo); the DB is never changed |
| `GET /ledger?limit=10` · `GET /ledger/anchors` | public | Recent blocks; daily Merkle roots |
| `GET /public-keys` | public | Signing public keys |
| `GET /dashboard/overview` · `/dashboard/journeys` · `/dashboard/journeys/{id}` · `/dashboard/receipts` · `/dashboard/rescue-tasks` | admin | Dashboard data |
| `GET /dashboard/stream` | admin | SSE events: `journey.updated`, `receipt.created`, `rescue.created`, `guard.blocked`. The browser sends the token in a header via `fetch-event-source`; never put tokens in URLs |
| `POST /admin/demo/reset` · `POST /admin/demo/abandoned-journey` | admin (dev) | Demo controls |
| `POST /admin/kfs/upload` · `GET /admin/kfs/{id}` · `POST /admin/kfs/{id}/verify` · `POST /admin/kfs/{id}/publish` | admin | KFS ingestion (Phase 10) |
| `POST /rescue/{task_id}/accept` | owner | Resume the journey from a rescue call |

**Card actions** (`input.action` for taps): `consent {purpose, granted}`, `confirm_field {field, value}`, `select_offer {offer_id}`, `quiz_answer {question_id, option_id}`, `accept_terms`, `insurance_addon {granted}`, `request_human`, `repeat`, `switch_language {language}`, `manual_form {fields}`.

### 8.2 `TurnResponse` (server-driven UI)
```ts
type Lang = "mr-IN" | "hi-IN" | "en-IN";
type Step = "INTRO" | "ASK_NEED" | "CONSENT_DATA" | "MANUAL_FORM" | "PREFILL" | "CONFIRM_DETAILS" | "OFFERS"
          | "EXPLAIN_KFS" | "TEACHBACK" | "TERMS_CONSENT" | "OTP" | "RECEIPT" | "DONE" | "HUMAN_HANDOFF";

interface TurnResponse {
  journeyId: string;
  step: Step;
  progress: { index: number; total: number; label: string; etaSeconds: number };
  language: Lang;
  messages: { id: string; role: "assistant" | "user"; text: string;
              audio?: { url: string; mime: "audio/mpeg" } }[];
  card?: { type: "consent" | "prefill" | "confirm" | "offers" | "kfs" | "quiz" | "consent_lock"
                 | "otp" | "receipt" | "handoff" | "manual_form"; data: unknown };
  quickReplies?: { label: string; value: string }[];
  transcript?: string;          // voice turns only
  detectedLanguage?: Lang;      // voice turns only
  locks?: { acceptEnabled: boolean; reason?: string };
}
```
Define matching Pydantic models in `journey/responses.py` and generate the TS types by hand into `frontend/src/lib/types.ts`. They must stay in sync, and a test compares the field names.

---

## 9. Journey engine (state machine)

```
INTRO → ASK_NEED → CONSENT_DATA → PREFILL → CONFIRM_DETAILS → OFFERS → EXPLAIN_KFS → TEACHBACK → TERMS_CONSENT → OTP → RECEIPT → DONE
            ↘ (declined) MANUAL_FORM ↗          any step → HUMAN_HANDOFF        idle → ABANDONED → (rescue) resume same step
```

**Core principle:** `engine.transition(state, understood_input) → (new_state, response)` is deterministic code. The LLM (Phase 7) only fills `understood_input` and paraphrases text. Every transition writes an `audit_log` event.

Step rules:
- **ASK_NEED:** extract the amount (₹10,000–₹2,00,000) and purpose. Ask again at most once; if still unclear, show amount chips (₹25,000 / ₹50,000 / ₹1,00,000).
- **CONSENT_DATA:** separate consents per purpose, default off. Declining leads to `MANUAL_FORM` (a short form card). Never block the journey because data sharing was declined.
- **PREFILL:** call the adapters (mock latency 0.8–1.5 s each, run in parallel) and show the sources. Adapters follow interfaces in `adapters/base.py`; mock implementations return persona data; `Real*` classes raise `NotImplementedError` with a docstring explaining the production integration (DigiLocker partner API, AA via a licensed provider).
- **CONFIRM_DETAILS:** 2 fields; "हो" confirms, "Edit" opens inline edit.
- **OFFERS:** `suitability.py` computes FOIR = (existing EMI + new EMI) / average monthly income. Pass if ≤ 50%; age 21–60; amount ≤ 3× monthly income. It returns human-readable reasons. `offers.py` returns **all eligible offers sorted by APR**, flags `lowest_total_cost` and `low_rate_high_fee`. The user picks by voice or tap.
- **EXPLAIN_KFS:** speak `explain_1`, `explain_2` and `explain_3`, and show the `kfs` card (a `Skip audio` chip lets her move on). "समजलं नाही" (didn't understand) replays a simpler version.
- **TEACHBACK:** questions Q1, Q2, Q3 (Q4 is the spare). Each has up to 3 attempts (1 + 2 re-explanations). Record `first_attempt_correct`. If still wrong after 3 attempts → `HUMAN_HANDOFF` (consent stays locked, status `needs_human`).
- **TERMS_CONSENT:** `acceptEnabled` is true only if all teach-back questions passed. Loan consent is an explicit tap (default No). The insurance add-on is a separate toggle, default off.
- **OTP:** 6 digits, hashed, expires in 5 minutes, 3 attempts. Typed only.
- **RECEIPT:** build and append the receipt (§11) and the customer summary; emit an SSE `receipt.created` event.
- **Backend guard:** `accept_terms` and OTP verify return **409** unless teach-back passed, loan consent was granted and the OTP verified, even if the frontend is bypassed. Tests cover this.

State storage: `journeys.step` + `journeys.context` (JSONB), with an optimistic `version` column to avoid double-processing a turn.

---

## 10. Sarvam AI integration (ears, brain, mouth, eyes)

Sarvam is the hackathon's official AI partner. Base URL `https://api.sarvam.ai`. Auth header `api-subscription-key: <SARVAM_API_KEY>`; the chat endpoint also accepts `Authorization: Bearer <key>`. **Before coding each Sarvam call, re-check the field names against the current docs (docs.sarvam.ai), because the API evolves.** All calls go through `ai/sarvam_client.py`: async httpx with timeouts, 1 retry on 429/5xx with jitter, structured errors, and latency logging without PII.

| Job | Model | Endpoint | Key settings |
|---|---|---|---|
| Ears: speech → text | `saaras:v4` | `POST /speech-to-text` (multipart: `file`, `model`, `language_code`, optional `keyterms`) | `language_code` = journey language, or `unknown` to auto-detect; keyterms `["Paytm","Spasht","EMI","CIBIL","KFS","DigiLocker","Account Aggregator","UPI AutoPay"]`; clips ≤ 25 s; response `transcript`, `language_code`, `language_probability` |
| Mouth: text → speech | `bulbul:v4-flash` (fallback `bulbul:v3`) | `POST /text-to-speech` (JSON: `text`, `language_code`, `speaker`, `model`, `pace`, `speech_sample_rate`, `output_audio_codec`) | `output_audio_codec: "mp3"`, `speech_sample_rate: 24000`, `pace: 1.0`; response `audios[0]` base64 |
| Brain: understand, explain, grade | `sarvam-105b-conversations` for live turns; `sarvam-105b` for offline tasks | `POST /v1/chat/completions` | `temperature 0.2`; **disable reasoning for live turns** (`reasoning_effort: null`); `response_format: {"type":"json_schema", ...}` for structured outputs; `max_tokens` 300 for live turns |
| Eyes: read KFS PDF | Sarvam Document Intelligence (Sarvam Vision) | `POST /doc-ai/v1/job/extract` (multipart: `file` + `schema`, an inline JSON-schema string where every field has a `type` and a `description`) → `job_id`; poll `GET /doc-ai/v1/job/{job_id}/status` until `completed`; then `GET /doc-ai/v1/job/{job_id}/results` → `result` + `annotations` (per-field `confidence` and `sources`). The `sarvamai` SDK wraps the same calls | Offline, during KFS ingestion only (Phase 10) |

**Voices (`bulbul:v4-flash`):** Marathi `ishita_mr_conversational` (alternate `ritu_mr_insurance`); Hindi `ritu_hi_banking` (alternate `ishita_hi_banking`); English `ishita_en_customer`. Fallback for `bulbul:v3`: speaker `ishita`. Put this voice map in config.

### 10.1 STT details (`ai/stt.py`)
- Browser recording: `MediaRecorder` with `audio/webm;codecs=opus` (Chrome/Android) or `audio/mp4` (iOS Safari). Saaras accepts WebM and MP4/M4A, so upload as-is. Max upload 2 MB; reject other MIME types.
- If `language_probability` is low or the transcript is empty → `didnt_catch` reply plus a typing fallback hint.
- If the detected language differs from the journey language for 2 turns in a row → offer to switch (quick reply), or switch automatically when the user explicitly asks ("हिंदी में बोलो").

### 10.2 TTS details (`ai/tts.py`, `ai/speakable.py`)
- `speakable(text, lang)` converts display text to speech-friendly text: `₹4,600` → `4,600 रुपये` (mr/hi) / `4,600 rupees` (en); `18.67%` → `18.67 टक्के` / `18.67 प्रतिशत` / `18.67 percent`; `CIBIL` → `सिबिल`, `KFS` → `के एफ एस`, `APR` → `ए पी आर` (mr/hi). Keep commas in numbers above 4 digits (Sarvam recommends this).
- Cache: key = HMAC-SHA256(`TTS_CACHE_SECRET`, model | speaker | lang | speakable_text) → `backend/.cache/tts/<key>.mp3`, served at `/api/audio/<key>.mp3`. Because the key can't be guessed, the route needs no auth header. `make tts-cache` pre-generates every template line for the golden persona in all 3 languages.
- iOS Safari only plays audio after a user gesture: unlock an `AudioContext` and the audio element on the first tap (login or mic).

### 10.3 Brain (`ai/llm.py`, `understand_llm.py`, `explain.py`, `grade.py`, `reexplain.py`)
Where the LLM is used:
1. **Understand** free speech when the rules in §7.5 are not confident. Output JSON schema: `{intent: "provide_need"|"yes"|"no"|"choose_offer"|"answer_quiz"|"didnt_understand"|"want_human"|"switch_language"|"question_about_terms"|"other", amount?: number, purpose?: string, offer_id?: string, quiz_option_id?: string, free_answer?: string, language?: string, distress?: boolean}`.
2. **Answer questions about the KFS** ("foreclosure kasa karaycha?"): retrieve matching clauses with Postgres full-text search on `kfs_clauses`, then answer in ≤ 2 sentences **using only those clauses and facts**. If nothing matches → "I'll connect you to an expert" (no guessing).
3. **Grade free-form teach-back answers** against the rubric → `{correct: bool, confidence: 0..1, missing_concept?: string}`. If confidence < 0.6 → ask her to pick an option (tap fallback). Keyword grading runs first; the LLM is a second opinion.
4. **Re-explain** with an everyday example when an answer is wrong: ≤ 2 sentences, must pass the Number Guard; otherwise use the seeded `reexplain` text.

**System prompt (`ai/prompts/system.md`), key rules:**
- You are Spasht, a polite assistant inside the Paytm app helping a customer understand a loan in {LANGUAGE}. Reply only in {LANGUAGE}, using respectful forms (तुम्ही / आप).
- Use **only** the facts provided in `<facts>`. **Never write a number that is not in `<facts>`**; use the placeholders `{EMI}`, `{TOTAL_REPAY}` and so on instead.
- No financial advice beyond the document. No pressure, urgency or upselling. Always say insurance is optional.
- **Never ask for an OTP, PIN, password, or Aadhaar/PAN number by voice.**
- If the user seems confused twice or distressed, offer a human expert.
- At most 2 short sentences per reply. Off-topic requests: politely decline and steer back.

### 10.4 Latency budget (per voice turn, target < 4 s)
Upload + STT ≤ 1.5 s · engine (rules first, LLM only if needed) ≤ 1.5 s · TTS ≤ 1 s (cache hit ≈ 0). Show `Thinking…` with an earcon after 400 ms. Template replies are preferred during the golden path; the LLM is used for understanding fallbacks, KFS questions and re-explanations.

### 10.5 Number Guard (`ai/number_guard.py`), critical and tested
- Allowed set = the numeric facts of the offers on screen (all offers at the OFFERS step, only the selected offer after that: principal, EMI, total repay, interest, total cost, rate, APR, fees, GST, late fee, foreclosure %, cooling-off days, insurance premium, tenure), the customer's verified figures shown on screen (requested amount, average income, EMI-to-income %), plus small counts `{1, 2, 3}`.
- Normalise before checking: Devanagari digits → ASCII; remove commas and spaces inside numbers; expand हजार/हज़ार/thousand and लाख/lakh; handle `%`, `टक्के`, `प्रतिशत`, `₹` and `रुपये`.
- Any number outside the allowed set → reject the LLM text, fall back to the template, and write an `audit_log` event `guard.blocked`. This becomes a dashboard metric: "AI numbers blocked: N".
- Tests: allowed numbers pass; an invented "₹4,000" EMI is blocked; Devanagari "४,६००" passes; "18.5%" is blocked.

### 10.6 Demo and offline mode (`DEMO_MODE=true`, or automatic when Sarvam is unreachable)
- STT → a "canned transcript" picker in the dev panel (golden-path utterances per step), plus typing.
- TTS → cached MP3s from `make tts-cache`; if a line is missing, show text only.
- LLM → templates and rule-based understanding only.
- The header shows a small `Demo mode` chip so the team knows.

### 10.7 Evaluation (`backend/evals/`)
`utterances.jsonl` holds 40+ cases (mr/hi/en and code-mixed, with expected intent and slots, plus wrong and right teach-back answers). `make eval` prints accuracy per intent and writes `docs/EVAL.md`. Target ≥ 90% on golden-path cases.

---

## 11. Trust layer: the Spasht Receipt

### 11.1 Payload (example)
```json
{
  "receipt_no": "SP-7F3A9C2K",
  "seq": 42,
  "journey_id": "…",
  "customer_ref": "sha256(user_id + PEPPER)",
  "customer_display": "Sunita J.",
  "mobile_masked": "+91 98•••••210",
  "product": "personal_loan",
  "lender": "Partner NBFC A",
  "offer_id": "offer_a",
  "kfs": { "id": "…", "version": "v3.2", "file_sha256": "9c1e…a47f" },
  "facts_explained": ["emi","total_repay","late_fee","foreclosure_pct","insurance_optional","cooling_off_days"],
  "language": "mr-IN",
  "channel": "paytm_app_voice",
  "teachback": [
    { "q": "q_late_fee", "attempts": 2, "first_attempt_correct": false, "passed": true },
    { "q": "q_total_repay", "attempts": 1, "first_attempt_correct": true, "passed": true },
    { "q": "q_insurance_optional", "attempts": 1, "first_attempt_correct": true, "passed": true }
  ],
  "suitability": { "foir": 0.162, "decision": "suitable", "reasons": ["EMI is 16% of verified income"] },
  "consents": [
    { "purpose": "fetch_digilocker", "granted": true, "method": "tap", "at": "…" },
    { "purpose": "fetch_account_aggregator", "granted": true, "method": "tap", "at": "…" },
    { "purpose": "loan_terms", "granted": true, "method": "tap+otp", "at": "…" },
    { "purpose": "insurance_addon", "granted": false, "default": false, "at": "…" }
  ],
  "timestamps": { "started": "…", "completed": "…" },
  "app_version": "spasht-0.1.0"
}
```

### 11.2 Chain and signature
- `canonical(payload) = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, UTF-8.
- `hash = sha256(prev_hash + canonical)` as hex. The genesis `prev_hash` is 64 zeros.
- `signature = Ed25519.sign(bytes.fromhex(hash))` with the server key (PyNaCl), base64. `signing_key_id` is stored; public keys are exposed at `/api/public-keys`. `make keys` generates the keypair into `backend/secrets/` (gitignored).
- Appends are serialised: `SELECT … FROM ledger_head WHERE id = 1 FOR UPDATE` inside the transaction, then insert the receipt and update the head. A concurrency test with parallel appends must keep the chain valid.
- `receipt_no` = `SP-` + 8 Crockford base32 characters from 40 random bits (about a trillion values, so numbers can't be guessed; retry on collision). It is inside the payload.
- Transcripts are encrypted at rest with AES-256-GCM (`trust/crypto_box.py`, key `TRANSCRIPT_KEY`); only the dashboard decrypts them, for admins.

### 11.3 Verification (`trust/verify.py`)
Checks returned as a list: ① payload hash matches the stored hash; ② `prev_hash` equals the previous receipt's hash (chain link); ③ the Ed25519 signature is valid for the stored key; ④ the KFS file hash matches the stored KFS document. `verify-candidate` runs ①–③ on an edited copy and returns the field-level diff and **TAMPERED** reasons. Nothing in the DB changes. Without login, the verify page shows the checks and a minimal summary; the full masked payload and the tamper simulation need the owner's or an admin's login (the demo laptop is signed in as admin).

### 11.4 Daily anchor (Merkle root)
`trust/merkle.py`: a binary SHA-256 Merkle tree over the day's receipt hashes in `seq` order (duplicate the last leaf when the count is odd). It is stored in `daily_anchors` and shown on the dashboard as "Today's anchor", which could be published for auditors.

### 11.5 Customer summary
A templated one-page summary in her language: lender, EMI, total repay, the red flags, "insurance: not taken", the cooling-off right, the receipt number and a QR to `/verify/:no`. It is shown as a mock chat-message preview (nothing is actually sent).

---

## 12. Lender and compliance dashboard

Admins only: Firebase Google login plus the `DASHBOARD_ADMIN_EMAILS` allowlist.

- **Overview KPIs:** journeys started today · completed · completion % · median time to complete · teach-back first-attempt pass % · re-explanations · human handoffs · language split (mr/hi/en) · insurance add-on opt-in % (low means no forced bundling) · AI numbers blocked by the guard.
- **Charts (Recharts):** funnel by step (where people drop); **first-attempt pass rate per teach-back question.** This is a product insight for lenders: if 40% misunderstand the late fee, the KFS wording needs work.
- **Live journeys:** a table updated over SSE (persona, language, step, status, duration, last activity) with a pulsing dot for active journeys.
- **Journey detail drawer:** event timeline from `audit_log`, decrypted transcript with replay, teach-back attempts, consents, suitability, receipt link.
- **Receipts:** table (no., seq, short hash, created, a `Verify` button that shows the checks inline).
- **Ledger:** the last 10 blocks drawn as linked cards (prev → hash), plus today's Merkle anchor.
- **KFS library (Phase 10):** versions, status, upload and verify flow.
- **Rescue tasks (Phase 9).**
- **Demo controls (dev only):** reset demo data, switch persona, create an abandoned journey, toggle demo mode.

---

## 13. Security, privacy and compliance rules

- Verify the Firebase ID token on every protected route (`firebase_admin.auth.verify_id_token`). Initialise `firebase-admin` with `FIREBASE_PROJECT_ID`; a service-account JSON is optional. If verification asks for credentials on a machine, use `google-auth`'s `id_token.verify_firebase_token` with `audience=FIREBASE_PROJECT_ID` instead.
- Never put tokens or personal data in URLs or query strings.
- Separate, purpose-wise consents with default **No** (aligned with the DPDP Act and RBI's consent rules). Store every consent append-only.
- No dark patterns: no pre-ticked boxes, no false urgency, declining is as easy as accepting, insurance is never pre-selected.
- The OTP is typed, never spoken; the assistant never asks for OTPs, PINs, passwords or ID numbers by voice.
- Mask PII in the UI and in receipts; redact phone, PAN and Aadhaar-like patterns in logs (logging filter); never log raw transcripts.
- Rate-limit `/voice/turn` (e.g., 30 per minute per user) and cap uploads at 2 MB.
- CORS is limited to the frontend origin; the Vite proxy is used in dev.
- Secrets live only in `.env` and `backend/secrets/`, all gitignored. Add a pre-commit secret scan if possible.
- Contact-window rule: the Rescue Agent only "calls" between 09:00 and 18:00 IST (configurable for the demo) and respects `dnd` and `consent_callbacks`.
- Synthetic data only; the concept-demo labels stay visible; no public deployment.

---

## 14. Environment variables

**`backend/.env.example`**
```
APP_ENV=dev
APP_VERSION=0.1.0
DATABASE_URL=postgresql+psycopg://spasht:spasht@localhost:5432/spasht
CORS_ORIGINS=http://localhost:5173
SARVAM_API_KEY=
SARVAM_BASE_URL=https://api.sarvam.ai
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v4-flash
SARVAM_TTS_FALLBACK_MODEL=bulbul:v3
SARVAM_LLM_LIVE_MODEL=sarvam-105b-conversations
SARVAM_LLM_OFFLINE_MODEL=sarvam-105b
FIREBASE_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=          # optional: ./secrets/firebase-service-account.json
DASHBOARD_ADMIN_EMAILS=                  # comma-separated
SIGNING_KEY_PATH=./secrets/ed25519_private.key
SIGNING_KEY_ID=spasht-07
TRANSCRIPT_KEY=                          # base64 32 bytes, generated by `make keys`
CUSTOMER_REF_PEPPER=                     # random string, generated by `make keys`
TTS_CACHE_SECRET=                        # random string, generated by `make keys`
DEMO_MODE=false
DEMO_AUTH=false
OTP_DEMO=true
RESCUE_IDLE_SECONDS=60
CONTACT_WINDOW=09:00-18:00
```

**`frontend/.env.example`**
```
VITE_API_BASE_URL=/api
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_APP_ID=
VITE_DEMO_AUTH=false
```

---

## 15. Phases 0 → 12 (the build)

**Order:** Phase 0 creates the project folder, Phase 1 adds login, and each later phase adds one part. Run them in order.

**Priority:** the hackathon minimum is **Phases 0–8, 11 and 12**. Phases 9 (Rescue) and 10 (KFS ingestion) are stretch goals; build them only if time allows. Rough effort is shown per phase.

**If time is short:** do 0 → 1 → 2 → 3 → 4 → 5 → 6 → 8 → 11 → 12, and in Phase 7 build only the Number Guard and KFS questions. The golden path already works with rule-based understanding.

---

### Phase 0 — Project folder and scaffold (≈ 1 h)
**Human first:** install Git, Docker Desktop (keep it running), Node 20+ LTS, Python 3.11+ and, ideally, `uv` (Appendix D).

**Build:**
1. Create the structure from §4 inside `spashtpaytm/`; `git init`; `.gitignore` (node_modules, dist, `.env` and `.env.*` except `.env.example`, backend/secrets/, backend/.cache/, __pycache__, .venv, *.pem, *.key, *service-account*.json, docs/reference/); `.editorconfig`.
2. Write `CLAUDE.md` (Appendix A), `docs/PROGRESS.md` (all phases as unchecked boxes), `docs/DECISIONS.md`, and a README skeleton.
3. `infra/docker-compose.yml`: `postgres:16-alpine` (user/password/db `spasht`, named volume, healthcheck) and `adminer` on 8080.
4. Backend: FastAPI app factory, `config.py` (pydantic-settings reading §14), SQLAlchemy engine and session, **Alembic initialised** with an empty baseline migration, JSON logging with a PII-redaction filter, `GET /api/health` (includes a DB check), ruff config, a first pytest.
5. Frontend: Vite + React + TS strict, Tailwind with the §5.2 tokens, fonts, React Router with two layouts (`PhoneFrame` for phone routes, `DesktopLayout` for `/dashboard`), TanStack Query, and a placeholder home that shows "Backend: OK · DB: OK" from `/api/health` through the Vite proxy.
6. Task runner: `Makefile` targets `setup`, `db-up`, `migrate`, `dev` (DB + uvicorn --reload + vite together), `test`, `lint`, **and a root `package.json` with npm scripts of the same names** (using `concurrently`), so `npm run dev` works on Windows too. Use `uv` for the Python environment if it is installed, otherwise `python -m venv`.

**Acceptance criteria:**
- [ ] `make setup && make dev` (or `npm run setup && npm run dev`) starts everything; `http://localhost:5173` shows "Backend: OK · DB: OK" inside the phone frame.
- [ ] `/dashboard` shows an empty desktop layout.
- [ ] `make lint` and `make test` pass. `git status` shows no secrets or screenshots tracked.

**Commit:** `phase-0: project folder, docker postgres, fastapi health, vite react shell`

---

### Phase 1 — Login with Firebase Google sign-in (≈ 1.5 h)
**Human first:** create the Firebase project, enable Google sign-in, register the web app, and fill both `.env` files (Appendix D). Add your team's Google emails to `DASHBOARD_ADMIN_EMAILS`.

**Build:**
1. DB: the `users` table from §6 as the first real migration (`persona_id` stays nullable, without a foreign key, until Phase 2).
2. Frontend: `lib/firebase.ts`, `AuthProvider` (`onAuthStateChanged`; call `getIdToken()` before each request so tokens refresh), the `LoginPage` per §5.5 with `signInWithPopup` started from a tap, route guards (phone routes need a signed-in user; `/dashboard` needs an admin), and an API client that attaches `Authorization: Bearer <idToken>`.
3. Backend: `auth/firebase.py` dependency that verifies the ID token (§13), upserts the user (name, email, photo) and marks admins from the allowlist; `GET /api/me` and `PATCH /api/me` (`preferred_language`).
4. `DEMO_AUTH` mode on both sides: "Continue as demo user" sends `X-Demo-User: sunita`. The backend accepts that header only when `DEMO_AUTH=true` and `APP_ENV=dev`.
5. A temporary signed-in home placeholder with the user's name, photo and a Logout button (Logout moves into the profile drawer in Phase 3).

**Acceptance criteria:**
- [ ] Google login works on the laptop; `/api/me` returns the user's name, email, photo, `preferred_language` and `is_admin`.
- [ ] Refreshing the page keeps the user signed in; Logout works.
- [ ] Protected routes return 401 without a token; `/dashboard` returns 403 for non-admins.
- [ ] Demo auth works with no internet.
- [ ] Auth tests use a mocked token verifier.

**Commit:** `phase-1: firebase google login, token verification, users table, demo auth`

---

### Phase 2 — Database and mock data (≈ 2 h)
**Build:**
1. SQLAlchemy models and Alembic migrations for the rest of §6, including the `forbid_update_delete()` triggers, the indexes, and the `users.persona_id` foreign key.
2. Seed JSON for §7.1–7.4 (personas, DigiLocker, CKYC, AA statements, lenders, offers, teach-back bank, templates) and an idempotent `make seed`.
3. Persona linking: on first login a user is linked to persona `sunita`; `/api/me` now returns the persona; `POST /api/me/persona` switches it (admin or dev only).
4. `journey/loan_math.py` with `emi`, `apr_irr`, `total_cost`, plus tests asserting the §7.2 table.
5. `scripts/generate_kfs_pdf.py` → three sample KFS PDFs in `app/assets/kfs/`; store each file's SHA-256, the facts and the clauses (`kfs_clauses` with `tsv`).
6. `make migrate`, `make seed`, `make demo-reset` (dev only: truncate journey-related tables and receipts, then re-seed).

**Acceptance criteria:**
- [ ] `make migrate && make seed` works twice in a row without duplicates.
- [ ] `/api/me` includes the linked persona `sunita`.
- [ ] An `UPDATE` or `DELETE` on `receipts`, `consents` or `audit_log` raises an error (test).
- [ ] Loan-math tests pass: A = ₹4,600 / ₹55,200 / 18.67%; B = ₹4,536 / fee ₹2,950 / ≈27.80%; C = ₹4,656 / 21.01%.
- [ ] The KFS PDFs open and look like real sample KFS documents; Adminer shows the seeded data.

**Commit:** `phase-2: schema, append-only triggers, seed data, loan math, sample KFS PDFs`

---

### Phase 3 — Paytm-style app shell and home screen (≈ 3 h)
**Build:**
1. UI components (Card, Chip, IconTile, BottomSheet, Drawer, Badge, Toast, Toggle, Skeleton) using the §5.2 tokens.
2. `HomePage` driven by `homeConfig.ts`, exactly following §5.3 (all 16 parts), with the Spasht entry points and the first-visit tooltip.
3. `ProfileDrawer` per §5.4, using the Google name and photo, a demo QR, the **functional language sheet** that saves `preferred_language`, Logout, and the non-functional Profile completion page.
4. `ConceptRibbon`, the "concept demo" bottom sheet for every non-Spasht tile, and `PhoneFrame` with safe areas.
5. PWA via `vite-plugin-pwa`: name "Spasht (Concept)", a simple generic "S" icon on navy (no Paytm icon), `display: standalone`, theme `#002E6E`.

**Acceptance criteria:**
- [ ] Side by side with the reference screenshots, the home screen has the same section order, spacing, card style, icon style and floating Scan QR pill.
- [ ] Loan → `/spasht`; every other tile shows the concept sheet; the avatar opens the drawer; the language setting persists.
- [ ] No official logos and no real partner logos are used; the concept ribbon is visible.
- [ ] Lighthouse: PWA installable; no console errors; smooth scrolling on a phone.

**Commit:** `phase-3: paytm-style home, profile drawer, concept guardrails, PWA`

---

### Phase 4 — Spasht journey, end to end without AI (≈ 4 h)
**Build:**
1. The backend journey engine (§9): `states.py`, `engine.py`, `understand_rules.py` (§7.5), `suitability.py`, `offers.py`, `teachback.py`, the templates, the mock adapters, and the `TurnResponse` models.
2. Endpoints: `POST /journeys`, `GET /journeys/{id}`, `POST /journeys/{id}/turn`, OTP send/verify (the receipt is a placeholder until Phase 5).
3. An `audit_log` event for every transition; consents written append-only.
4. Frontend: `SpashtIntro` (language choice) → `SpashtChat` with the stepper, bubbles, all cards from §5.6, quick replies and a text input. The mic button is visible but disabled ("voice comes in Phase 6").
5. The consent lock enforced in the UI **and** the backend (409 tests).

**Acceptance criteria:**
- [ ] The full golden path (§2) works by taps and typing in **mr, hi and en**, using the seeded templates.
- [ ] Bank B shows the `Lowest rate, but high fees` badge; offers are sorted by APR; NBFC A is `Lowest total cost`.
- [ ] A wrong quiz answer triggers the re-explanation; three wrong answers lead to `HUMAN_HANDOFF`.
- [ ] Declining data consent leads to the manual form and the journey still completes.
- [ ] The insurance toggle defaults off; accept without passing teach-back returns 409 (test).
- [ ] The DB shows the journey, consents, attempts and audit events.

**Commit:** `phase-4: deterministic spasht journey with server-driven UI and consent lock`

---

### Phase 5 — Trust layer: Spasht Receipt (≈ 2.5 h)
**Build:**
1. `trust/canonical.py`, `signing.py` (`make keys`), `ledger.py` (serialised append), `verify.py`, `merkle.py`, `crypto_box.py` (encrypt transcripts).
2. On OTP success: build the §11.1 payload, append it, generate the customer summary, emit `receipt.created`.
3. Endpoints: receipt get, verify, verify-candidate, ledger, anchors, public keys.
4. Frontend: `ReceiptCard` in the journey (stamp animation, QR, chat-style summary preview); `VerifyPage` with the 4 checks (a minimal public view, plus the full view and the **"Simulate tampering"** editor for the owner or an admin: edit EMI, language or an answer → ✗ with the field diff); `LedgerChain` component.

**Acceptance criteria:**
- [ ] The golden path ends with a real receipt; `/verify/SP-…` shows 4 green checks.
- [ ] Editing any field in the tamper editor shows ✗ TAMPERED with reasons; the DB is unchanged.
- [ ] Signed out, `/verify/SP-…` shows only the minimal view; signed in as admin, the full payload and the tamper editor appear.
- [ ] Tests: tamper detection, chain-break detection, wrong-key signature failure, and 20 parallel appends keeping the chain valid.

**Commit:** `phase-5: hash-chained signed receipts, verify page, tamper demo, merkle anchors`

---

### Phase 6 — Voice with Sarvam: ears and mouth (≈ 3 h)
**Human first:** put `SARVAM_API_KEY` in `backend/.env` (Appendix D).

**Build:**
1. `ai/sarvam_client.py`, `stt.py`, `tts.py`, `speakable.py`, the TTS cache, and `make tts-cache`.
2. `POST /api/voice/turn`: STT → rule-based understanding (Phase 4) → engine → TTS → `TurnResponse` with transcript and audio URL; latency fields stored in `conversation_turns`.
3. Frontend: `useRecorder` (MIME negotiation, 25 s cap, level meter for the waveform), `MicButton` (press-and-hold and tap toggle), `useAudioPlayer` (queue, replay, iOS unlock), the Listening/Thinking/Speaking states, captions, language-switch handling.
4. Demo/offline mode (§10.6) with the canned-transcript picker and the `Demo mode` chip.

**Acceptance criteria:**
- [ ] The golden path works **fully by voice in Marathi** on a laptop (Chrome), with captions and spoken replies.
- [ ] Hindi and English work; code-mixed speech ("mujhe loan chahiye for machine") is understood.
- [ ] Median voice-turn latency < 4 s (logged); a cached TTS line plays instantly.
- [ ] With the network off (or `DEMO_MODE=true`), the demo still completes using the picker and cached audio.

**Commit:** `phase-6: sarvam saaras stt + bulbul tts voice loop with cache and demo mode`

---

### Phase 7 — The brain with Sarvam-105B (≈ 4 h)
**Build:**
1. `ai/llm.py` (chat completions client, structured outputs, reasoning off for live turns), the prompts in `ai/prompts/`.
2. `understand_llm.py` as a fallback when the rules aren't confident; `explain.py`; KFS question answering over `kfs_clauses` full-text search; `grade.py`; `reexplain.py`.
3. `number_guard.py` (§10.5) wrapping every LLM text output, with `guard.blocked` audit events.
4. Guardrails from §10.3, including human handoff on distress or repeated confusion.
5. `backend/evals/` with 40+ utterances and `make eval` → `docs/EVAL.md`.
6. Optional: orchestrate the nodes with LangGraph if it installs and works within 30 minutes; otherwise keep the plain state machine and note it in `DECISIONS.md`. Optional Langfuse tracing with redaction.

**Acceptance criteria:**
- [ ] Free-form answers ("late zala tar fine lagel na?") are graded correctly; a wrong answer gets an LLM re-explanation that passes the Number Guard.
- [ ] Asking "loan lavkar band kela tar kiti charge?" (what if I close early?) answers from the KFS clause, in Marathi, using the 4% fact.
- [ ] Number Guard tests pass (invented numbers are blocked).
- [ ] Eval ≥ 90% on golden-path utterances; results saved to `docs/EVAL.md`.

**Commit:** `phase-7: sarvam-105b understanding, KFS Q&A, grading, re-explain, number guard, evals`

---

### Phase 8 — Lender and compliance dashboard (≈ 3 h)
**Build:** everything in §12 except the KFS library and rescue tasks: `events/bus.py` (in-process pub/sub) + SSE stream with polling fallback, overview KPIs, the funnel chart, the per-question pass-rate chart, live journeys, the journey detail drawer, receipts with inline verify, the ledger view, demo controls.

**Acceptance criteria:**
- [ ] Finishing the golden path on the phone shows the journey and receipt on the laptop within 2 s without a refresh.
- [ ] KPIs and charts reflect the seeded and live data; verify from the dashboard works.
- [ ] Only allowlisted admins can open the dashboard.

**Commit:** `phase-8: live compliance dashboard with SSE, KPIs, ledger and receipts`

---

### Phase 9 — Rescue Agent (stretch, ≈ 2 h)
**Build:**
1. `rescue/scheduler.py`: a background loop every 15 s finds journeys idle for `RESCUE_IDLE_SECONDS` at PREFILL, OFFERS or TEACHBACK and creates a `rescue_task` with a human-readable reason ("stuck at quiz Q1"). It respects `CONTACT_WINDOW`, `dnd` and `consent_callbacks`.
2. A simulated call: TTS of the `rescue_call` template in her language, plus an incoming-call UI on the phone (`/spasht/rescue/:taskId`) with Accept/Decline. Accept plays the audio and resumes the journey at the exact step.
3. Dashboard "Rescue tasks" page; the demo control "Create abandoned journey".
4. Document that real calls would use a telephony provider (e.g., Exotel) in production; not implemented.

**Acceptance criteria:**
- [ ] Demo control → within 60 s a rescue task appears → the phone shows the incoming call → Accept resumes at the right step.
- [ ] Outside the contact window, no "call" is made and the dashboard shows why.

**Commit:** `phase-9: rescue agent with contact-window rules and resume`

---

### Phase 10 — KFS ingestion with Sarvam Vision (stretch, ≈ 3 h)
**Build:**
1. Dashboard "KFS library": upload a PDF → Sarvam Document Intelligence **extract** job with a field schema (lender, principal, rate, fee, EMI, tenure, APR, late fee, foreclosure, cooling-off days, insurance optional, grievance contact) → poll → show the extracted fields next to a PDF preview.
2. **Human verification:** an admin must confirm or edit every field before publishing a new KFS version (store `verified_by`, `verified_at`, the file SHA-256).
3. On publish: generate teach-back questions and explanation lines in mr/hi/en with `sarvam-105b` (structured output), run them through the Number Guard, show them for review, then activate.
4. Offline fallback: parse our own generated PDFs with `pdfplumber` when the API is unavailable.

**Acceptance criteria:**
- [ ] Uploading Partner Bank B's KFS → extracted facts → admin verifies → a new journey on the phone uses the new facts and questions.
- [ ] Nothing is published without human verification.

**Commit:** `phase-10: KFS ingestion with sarvam document intelligence and human verification`

---

### Phase 11 — Polish, reliability and QA (≈ 3 h)
**Build:**
1. A visual polish pass against the screenshots; loading skeletons; empty and error states; micro-animations; dark-text contrast checks.
2. Failure handling: mic permission denied → typing; STT error → `didnt_catch`; TTS error → text only; LLM timeout → template; backend down → friendly error with retry.
3. Pre-warm on app load (health ping, prefetch the first TTS lines); the demo reset button; persona switcher.
4. Accessibility: aria labels, focus states, captions always on, font scaling.
5. Optional Playwright e2e test of the golden path in demo mode.
6. Docs: README (setup, run, demo, troubleshooting), `docs/ARCHITECTURE.md` (mermaid diagram), `docs/DEMO_SCRIPT.md` (Appendix E).

**Acceptance criteria:**
- [ ] The §16 QA checklist passes **twice in a row** from a fresh `make demo-reset`.
- [ ] Offline/demo mode completes the golden path.
- [ ] No console errors; lint and tests pass.

**Commit:** `phase-11: polish, failure handling, demo reset, docs`

---

### Phase 12 — Phone setup and demo-day run (≈ 1 h)
**Human first:** install `cloudflared` or `ngrok` (Appendix D).

**Build:**
1. `make tunnel` (or documented commands) exposing the Vite server over HTTPS. Prefer ngrok's free static domain (or a named Cloudflare tunnel) so the URL stays the same and is added to Firebase **Authorized domains** only once. Add the tunnel host to Vite's `server.allowedHosts` (and `preview.allowedHosts`), because Vite blocks unknown hosts by default.
2. Verify on an iPhone (Safari → Share → Add to Home Screen) and an Android phone (Chrome); fix any iOS audio, recording or safe-area issues.
3. **Google sign-in on phones:** test `signInWithPopup` in the phone's browser tab first. If it fails in iOS home-screen (standalone) mode, apply Firebase's documented fix for browsers that block third-party storage: proxy `/__/auth/*` through the Vite server to `https://<project-id>.firebaseapp.com`, set `VITE_FIREBASE_AUTH_DOMAIN` to the tunnel host, and add `https://<tunnel-host>/__/auth/handler` to the OAuth client's authorized redirect URIs in Google Cloud. If it still fails, run the phone demo in the browser tab, or use "Continue as demo user" on the phone and keep real Google login on the laptop.
4. A production build option (`vite build` served by `vite preview` or FastAPI static files) for smoother performance.
5. A demo-day checklist in the README: hotspot, chargers, speaker, backup video, demo accounts logged in, `DEMO_MODE` toggle ready, dashboard open on the laptop.

**Acceptance criteria:**
- [ ] The golden path runs on a real phone over the tunnel by voice, and the laptop dashboard updates live.
- [ ] The backup video is recorded (human).

**Commit:** `phase-12: tunnel, device fixes, demo-day checklist`

---

## 16. QA checklists

**Golden path (run before every demo):**
- [ ] Login → home renders correctly; the concept ribbon is visible
- [ ] Loan tile → Spasht in Marathi; greeting audio plays
- [ ] Voice need → amount ₹50,000 understood
- [ ] Consent toggles default off → allow → prefill with 4 sources
- [ ] Confirm by "हो"
- [ ] Offers: B flagged "low rate, high fees"; A "lowest total cost"; choose A
- [ ] KFS 5 lines shown and spoken
- [ ] Q1 wrong → re-explain → correct; Q2 ✓; Q3 ✓
- [ ] Accept unlocks; insurance stays No; OTP typed
- [ ] Receipt stamp, number, QR, Marathi summary preview
- [ ] Laptop: journey and receipt appear live; Verify ✓; tamper → ✗

**Devices:** iPhone Safari PWA · Android Chrome · laptop Chrome · phone speaker loud enough · mic works in a noisy room.

**Failure modes:** airplane mode → demo mode completes · Sarvam key removed → demo mode · mic blocked → typing works · backend restart mid-journey → resume from `GET /journeys/{id}`.

---

## 17. Pitch ↔ build alignment

The deck's tech-stack slide should match what is really built. After each phase, update this table, and fix the slide before the final pitch.

| Deck says | Built in | Note / action |
|---|---|---|
| Saaras v4, Bulbul v4, Sarvam-105B | Phases 6–7 | ✓ |
| Sarvam Vision reads KFS | Phase 10 (stretch) | If skipped, say "roadmap" on the slide |
| LangGraph | Phase 7 (optional) | If not used, change to "state-machine orchestrator" |
| pgvector RAG | Phase 7 uses Postgres full-text search | Change the slide to "Postgres search over KFS clauses", or add pgvector later |
| XGBoost drop-off model | Not in the MVP | Change to "rules-based now, ML on pilot data later" |
| SHA-256 chain, Ed25519, Merkle roots, AES-256-GCM | Phase 5 | ✓ |
| DigiLocker, AA, CKYC, UPI AutoPay | Mocked adapters (Phase 4) | Say "mocked with synthetic data; production via partner APIs" |
| WebSockets | HTTP uploads + SSE | Change to "HTTP + Server-Sent Events" |
| Celery + Redis | In-process background loop | Change to "background jobs (Celery/Redis at scale)" |
| PostgreSQL | ✓ | Add Firebase Auth to the slide |
| Docker, AWS Mumbai | Docker locally | Keep AWS Mumbai as the "deployment target" |
| Langfuse | Optional in Phase 7 | Remove if not used |
| Exotel call-backs | Simulated in Phase 9 | Say "simulated in the demo" |

---

## Appendix A — `CLAUDE.md` (copy into the repo root in Phase 0)

```markdown
# CLAUDE.md — Spasht (spashtpaytm)

Read docs/BUILD_PLAN.md before any work. Build ONE phase at a time; stop after each phase and wait for "Go Phase N".

## Non-negotiables
- Never commit secrets (.env, backend/secrets/, keys, service-account JSON).
- The AI never invents numbers: all amounts, rates, fees and dates come from KFS facts in the DB; every LLM text passes number_guard.
- Only the backend creates receipts. receipts / consents / audit_log / teachback_attempts are append-only (DB triggers).
- Code decides journey transitions; the LLM only understands and phrases.
- Synthetic data only; mask identifiers. Never ask for OTP/PIN/password/ID numbers by voice.
- Paytm-style UI = layout and feel only. No official Paytm logo artwork or app icon, no third-party logos, visible "Concept demo" label, never deploy publicly, QR codes never encode upi:// URLs.
- Every voice action has a tap/type alternative. DEMO_MODE must always complete the golden path.

## Conventions
- Frontend: React + Vite + TS strict + Tailwind; server-driven journey UI from TurnResponse.
- Backend: FastAPI + SQLAlchemy 2 + Alembic + Postgres; all Sarvam calls through app/ai/sarvam_client.py.
- Ports: web 5173 (proxies /api), api 8000, postgres 5432, adminer 8080.
- Commands (make, or npm run with the same names on Windows): setup | dev | migrate | seed | keys | test | lint | eval | tts-cache | demo-reset | tunnel.
- Never put tokens or personal data in URLs. Never copy personal details from the docs/reference/ screenshots.
- End of phase: lint + tests + acceptance checklist + update docs/PROGRESS.md and docs/DECISIONS.md + commit "phase-N: ...", then STOP.
```

## Appendix B — Kickoff message (paste into Claude Code)

```text
You are building "Spasht" in this folder (spashtpaytm). First read docs/BUILD_PLAN.md completely, especially sections 0, 2, 5 and 15.
Confirm in 10 lines: the product, the golden demo path, the stack, and the phase rules.
Then do Phase 0 only, exactly as written in the plan. At the end, run lint/tests, show the Phase 0 acceptance checklist with ✅/❌, give me manual test steps, commit, and STOP. Do not start Phase 1 until I say "Go Phase 1".
If anything in the plan is unclear or a tool/version is unavailable, ask me before deviating, then record the decision in docs/DECISIONS.md.
```

## Appendix C — Per-phase and fix-up messages

**Start the next phase:**
```text
Go Phase N. Re-read the Phase N section of docs/BUILD_PLAN.md and the relevant design/API sections it references. Restate the plan briefly, list files you'll touch, then build it. Finish with lint/tests, the acceptance checklist (✅/❌), manual test steps, update PROGRESS.md and DECISIONS.md, commit, and STOP.
```

**Something is broken:**
```text
The golden path breaks at step X with this error: <paste>. Reproduce it, find the root cause, fix it with the smallest change, add a test that would have caught it, rerun all tests, and show me the result. Don't change unrelated behaviour.
```

**Match the screenshots more closely:**
```text
Compare the home screen with the reference screenshots in docs/reference/ (I've added them). List the visible differences (spacing, sizes, colours, icon style, order), then fix them one by one. Keep the brand guardrails from section 5.1.
```

**Pre-demo check:**
```text
Run make demo-reset, then walk the section 16 QA checklist in DEMO_MODE and in live mode. Report each item ✅/❌ and fix any ❌ before telling me it's ready.
```

Tip: copy the reference screenshots into `spashtpaytm/docs/reference/` so Claude Code can look at them while building Phase 3. **Crop out or blur personal details** (name, UPI ID, bank digits) first.

## Appendix D — Human setup steps

1. **Tools:** Git, Docker Desktop, Node 20+ LTS, Python 3.11+, `uv` (recommended), and later `ngrok` (or `cloudflared`). On Windows, use the `npm run …` commands if `make` is not installed.
2. **Sarvam API key:** sign up on the Sarvam dashboard, create an API key (new accounts get ₹100 of free credit), and put it in `backend/.env` as `SARVAM_API_KEY`. The hackathon also offers Sarvam credits to participants who build with it.
3. **Firebase (Google login):**
   - Firebase console → **Add project** (e.g., `spashtpaytm`).
   - **Build → Authentication → Get started → Sign-in method → Google → Enable**, and choose a support email.
   - **Project settings → General → Your apps → Web (</>)** → register the app → copy `apiKey`, `authDomain`, `projectId`, `appId` into `frontend/.env`; put `projectId` into `backend/.env` as `FIREBASE_PROJECT_ID`.
   - **Authentication → Settings → Authorized domains:** `localhost` is there by default; add the tunnel domain in Phase 12.
   - Optional: **Project settings → Service accounts → Generate new private key** → save as `backend/secrets/firebase-service-account.json` (never commit it).
4. **Admin emails:** your team's Google emails in `DASHBOARD_ADMIN_EMAILS`.
5. **Phone over HTTPS (Phase 12):** claim ngrok's free static domain and run `ngrok http 5173 --url=<your-domain>` (older ngrok versions use `--domain`), or run `cloudflared tunnel --url http://localhost:5173` (quick tunnels get a new address on every run). Open the `https://…` link on the phone and add that domain to Firebase authorized domains. Share the link only with your team, and stop the tunnel after the demo.
6. **Marathi and Hindi review:** have a native speaker on the team read every string in §7.3–7.4 once.

## Appendix E — Demo script (3–4 minutes)

1. **(20 s) The problem:** show an English KFS PDF and a tick box. "Sunita can't read this, so she ticks 'I agree'."
2. **(90 s) Live on the phone:** Paytm-style home → Loan (Spasht) → speak Marathi → consent → auto-filled → offers ("lowest rate isn't cheapest") → 5-line KFS.
3. **(40 s) Teach-back:** answer Q1 wrong on purpose → simpler explanation → correct → Q2, Q3 → "I agree" unlocks, insurance stays No → OTP.
4. **(30 s) Proof:** receipt stamp → turn the laptop to the judges → the journey is already there → Verify ✓ → change the EMI → ✗ TAMPERED.
5. **(20 s) Why it matters:** "From 1 Jan 2027, RBI requires informed, recorded consent and a suitability check. Spasht makes compliance faster than the old flow, and Paytm can offer it to its lending and insurance partners through Pi."
6. **Backup:** if the network fails, switch on demo mode (cached voice) or play the recorded video.
