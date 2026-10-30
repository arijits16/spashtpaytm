# Demo script and demo-day checklist

Build plan Appendix E and §16, written out as the thing you actually read on the
day. Four minutes on stage, and everything that has to be true before them.

---

## Before you leave the house

- [ ] `make demo-reset` — journey data wiped, ledger reset, seed reloaded.
- [ ] `make tts-cache` — every golden-path line is pre-generated, so the
      assistant speaks instantly and a dead network cannot silence it.
- [ ] `make golden-path ARGS=--all` — the backend completes in all three
      languages and the receipt verifies. Run it twice.
- [ ] `make test && make lint && make audit` — green.
- [ ] The app reinstalled on each team iPhone **within the last 7 days** (a free
      Apple team expires the build after 7 days).
- [ ] The backup video recorded, on the laptop, playable offline.

## At the venue, 15 minutes before

- [ ] `make db-up` and `make dev` running. `GET /api/health` returns `ok`.
- [ ] `make tunnel` up on the ngrok **static** domain, so the URL in
      `ios/Config/Secrets.xcconfig` still matches and the app needs no rebuild.
- [ ] `GET /api/health` opened in Safari **on the phone** — the single fastest
      proof that the phone can reach the laptop.
- [ ] Dashboard open on the laptop at `/dashboard`, signed in as an admin,
      the connection badge reading **live**.
- [ ] Phone: volume **up**, Do Not Disturb **on**, screen-lock long, hotspot
      ready as the backup network, charger in the bag.
- [ ] Phone mirrored to the laptop: QuickTime Player → File → New Movie
      Recording → the arrow beside the record button → choose the iPhone.
      Check the privacy cover does not fire while mirroring.
- [ ] `make demo-reset` one last time, so the ledger starts clean on the
      projector.

---

## The script (3–4 minutes)

### 1. The problem — 20 s

Hold up the English KFS PDF and point at a tick box.

> "This is what the law requires a lender to hand Sunita before she signs. It is
> eleven pages of English. She cannot read it, so she ticks *I agree* — and
> nobody, including the lender, can show what she actually understood."

### 2. The journey, live on the iPhone — 90 s

Paytm-style home screen → **Loans & Insurance** → **Loan** → Spasht → मराठी.

> "Everything else on this screen is a concept shell. This one tile is real."

- She **speaks**: *"मला पन्नास हजार रुपये कर्ज हवे आहे"* — hold the mic, release.
- Consent toggles start **off**. Allow → details prefill from four sources
  (DigiLocker, Account Aggregator, CKYC, the shop's own records) → "हो".
- **Offers.** Three cards, sorted by **APR**, not by headline rate.

> "Bank B advertises the lowest rate. It is the most expensive loan on this
> screen, because of a ₹2,500 fee. We sort by what it actually costs."

- Pick A → **the KFS in five lines**, red flags first, spoken in Marathi.

### 3. Teach-back — 40 s

- Answer **Q1 wrong on purpose.** A simpler explanation comes back.
- Answer it right. Q2, Q3 — haptics on each pass.
- **"I agree" unlocks only now.**

> "The button was not disabled as decoration. The lock is enforced on the
> server: if the app sent the tap anyway, it would be refused."

- Insurance stays **No** — and the loan terms do not change.
- OTP typed.

### 4. The proof — 30 s

Receipt stamp on the phone. **Turn the laptop to the judges.**

> "The journey is already here. Nobody refreshed anything."

- The receipt row, the ledger block, the chain link to the previous receipt.
- **Verify ✓** — four checks: payload hash, chain link, Ed25519 signature, and
  the KFS PDF's own SHA-256.
- **Simulate tampering:** change the EMI by one rupee → **✗ TAMPERED**, with the
  diff. The stored receipt is untouched and still verifies.
- Invite a judge to **scan the QR** on the phone with their own phone: it opens
  `/r/<receiptNo>` and shows ✓ without any of our software.

### 5. Why it matters — 20 s

> "From 1 January 2027 the RBI requires informed, recorded consent and a
> suitability check on every retail loan. Spasht makes that compliance *faster*
> than today's flow rather than slower — and Paytm can offer it to its lending
> and insurance partners through Pi."

### Optional, if there is time

- **The rescue agent.** Demo controls → *Create an abandoned journey*. Within
  about fifteen seconds the phone rings: "Spasht · Paytm Loans". Accept resumes
  at the exact step. Then point at the rescue page: a task outside the contact
  window, or for someone on DND, says *why no call was placed*.
- **The KFS library.** Upload Bank B's PDF → the extracted fields with their
  confidence beside the document → correct the late fee → **Verify** → generate
  the teach-back questions → activate. The next journey quotes the new figure.

---

## Failure drills — rehearse each one once

| What breaks | What you do | What the audience sees |
|---|---|---|
| Wi-Fi dies | Switch to the hotspot | A retry bar, then the journey continues |
| Sarvam is down or slow | Nothing | Demo mode: templates and cached audio complete the path |
| The microphone is denied | Tap the keyboard button | "Microphone off — type instead", and typing works |
| The backend restarts mid-journey | Nothing | The app resumes on the exact step; the card rebuilds from `step` + `context` |
| The tunnel restarts | Nothing | The static domain is unchanged, so no rebuild |
| The phone will not cooperate at all | Play the backup video | A recording of this same script |

---

## The §16 golden-path checklist

Run it twice in a row from `make demo-reset`.

- [ ] The app opens to login or home; the concept ribbon is visible; the privacy
      cover works when you switch apps.
- [ ] Loan tile → Spasht → the Marathi greeting plays from the **speaker**.
- [ ] A spoken request for ₹50,000 is understood.
- [ ] Consent toggles start off → allow → prefill from 4 sources → "हो".
- [ ] Offers: B is "low rate, high fees", A is "lowest total cost" → choose A.
- [ ] The 5-line KFS is shown and spoken.
- [ ] Q1 wrong → re-explain → right; Q2 ✓ and Q3 ✓, with haptics.
- [ ] Accept unlocks; insurance stays No; the OTP is typed.
- [ ] Receipt stamp, number, QR and the Marathi summary preview.
- [ ] Laptop: the journey and the receipt appear live, within two seconds, with
      no refresh. Verify ✓; tamper → ✗.
- [ ] Second phone: the QR opens `/r/<no>` and shows ✓.

---

## After the event

- [ ] Stop the tunnel.
- [ ] Rotate `SARVAM_API_KEY` at <https://dashboard.sarvam.ai/>.
- [ ] Rotate `DEMO_AUTH_KEY` (and remove it from any device that kept it).
- [ ] Delete the app from any device that is not a team device.

---

## What to say if asked

- **"Is this the real Paytm app?"** No. It imitates the layout and feel so the
  journey can be judged in context. No official artwork, no real money, no real
  KYC, synthetic data only, never deployed publicly.
- **"Is the phone call real?"** No — it is an in-app screen. A real deployment
  would place it through a telephony provider such as Exotel (D-043).
- **"Does the AI decide anything?"** No. A deterministic state machine decides
  every transition; the model understands speech and phrases sentences, and
  every generated sentence passes the Number Guard. The generated teach-back
  text contains no digits at all — figures are placeholders filled from the
  verified Key Fact Statement.
- **"Where is the data from?"** `app/seed/data/*.json`, all invented. The
  lenders are fictional and every KFS PDF is watermarked SAMPLE.
