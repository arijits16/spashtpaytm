import { describe, expect, it } from "vitest";
import errorNotFound from "../../../contracts/fixtures/error_not_found.json";
import errorUnauthorized from "../../../contracts/fixtures/error_unauthorized.json";
import healthFixture from "../../../contracts/fixtures/health.json";
import meFixture from "../../../contracts/fixtures/me.json";
import type { Health, Me } from "@/lib/api";
import type { Card, CandidateResult, ReceiptDetail, TurnResponse, VerifyResult } from "@/lib/types";

/**
 * Load a fixture by name.
 *
 * `import.meta.glob` with `eager` so Vite inlines every fixture at build time:
 * the journey suite decodes seventeen of them, and seventeen static imports
 * would have to be kept in step with `make contracts` by hand.
 */
const fixtures: Record<string, unknown> = Object.fromEntries(
  Object.entries(
    import.meta.glob("../../../contracts/fixtures/*.json", { eager: true, import: "default" }),
  ).map(([path, value]) => [path.split("/").pop()!.replace(".json", ""), value]),
);

function load<T>(name: string): T {
  const fixture = fixtures[name];
  if (fixture === undefined) {
    throw new Error(`contracts/fixtures/${name}.json is missing. Run \`make contracts\`.`);
  }
  return fixture as T;
}

/**
 * Decode the shared contract fixtures (build plan 8.5).
 *
 * The backend generates `contracts/fixtures/*.json` with `make contracts`; the
 * iOS tests decode them with `Codable` and these check them against the
 * TypeScript types. TypeScript erases at runtime, so this asserts that the
 * fields the website actually reads are present and the right shape - which is
 * what catches a backend rename before the dashboard renders `undefined`.
 *
 * Imported rather than read with `fs`: Vite handles JSON natively, so the test
 * needs no Node type definitions and the fixtures are resolved the same way the
 * app resolves any other module.
 */

describe("contract fixtures", () => {
  it("health.json matches the Health type", () => {
    const health = healthFixture as Health;

    expect(["ok", "degraded"]).toContain(health.status);
    expect(typeof health.db).toBe("string");
    expect(["configured", "demo"]).toContain(health.sarvam);
    expect(typeof health.version).toBe("string");
    expect(typeof health.demoMode).toBe("boolean");
  });

  it("me.json matches the Me type", () => {
    const me = meFixture as unknown as Me;

    expect(typeof me.uid).toBe("string");
    expect(["mr-IN", "hi-IN", "en-IN"]).toContain(me.preferredLanguage);
    expect(typeof me.isAdmin).toBe("boolean");
    expect(["firebase", "demo"]).toContain(me.session);
    // `persona` is null for demo-admin, an object for a customer.
    expect(me.persona === null || typeof me.persona.id === "string").toBe(true);
  });

  it("me.json no longer carries the v1 field names", () => {
    // v1 had `id` and `personaId`; v2 has `uid` and a nested `persona`.
    const raw: Record<string, unknown> = meFixture;

    expect(raw).not.toHaveProperty("id");
    expect(raw).not.toHaveProperty("personaId");
  });

  it("the error fixtures use the standard envelope", () => {
    for (const body of [errorNotFound, errorUnauthorized]) {
      expect(typeof body.error.code).toBe("string");
      expect(typeof body.error.message).toBe("string");
      expect(typeof body.error.requestId).toBe("string");
    }
  });
});

// --- the journey and dashboard contracts (build plan 8.5) --------------------
//
// The website renders the journey detail drawer and the receipt check from
// these shapes, so a backend rename has to fail here rather than at demo time.

describe("journey fixtures", () => {
  const steps = [
    "turn_intro",
    "turn_consent",
    "turn_prefill",
    "turn_confirm",
    "turn_offers",
    "turn_kfs",
    "turn_quiz",
    "turn_quiz_wrong",
    "turn_terms_consent",
    "turn_otp",
    "turn_receipt",
    "turn_handoff",
    "turn_manual_form",
  ];

  it.each(steps)("%s decodes as a TurnResponse", (name) => {
    const turn = load<TurnResponse>(name);

    expect(typeof turn.journeyId).toBe("string");
    expect(typeof turn.step).toBe("string");
    expect(turn.progress.total).toBe(6);
    expect(["active", "completed", "needs_human"]).toContain(turn.status);
    expect(Array.isArray(turn.messages)).toBe(true);
    expect(turn.card).toBeTruthy();
  });

  it("offers are sorted by APR, and the lowest rate is the expensive one", () => {
    const turn = load<TurnResponse>("turn_offers");
    expect(turn.card?.type).toBe("offers");

    const card = turn.card as Extract<Card, { type: "offers" }>;
    const aprs = card.data.offers.map((offer) => offer.apr);
    expect(aprs).toEqual([...aprs].sort((a, b) => a - b));

    const cheapest = card.data.offers.find((offer) => offer.badges.includes("lowest_total_cost"));
    const trap = card.data.offers.find((offer) => offer.badges.includes("low_rate_high_fee"));

    expect(cheapest).toBeDefined();
    expect(trap).toBeDefined();
    // The demo's whole argument, asserted on the wire.
    expect(trap!.ratePa).toBeLessThan(cheapest!.ratePa);
    expect(trap!.totalCost).toBeGreaterThan(cheapest!.totalCost);
  });

  it("consent purposes arrive ungranted", () => {
    const turn = load<TurnResponse>("turn_consent");
    const card = turn.card as Extract<Card, { type: "consent" }>;
    expect(card.data.purposes.every((purpose) => !purpose.granted)).toBe(true);
  });

  it("insurance is optional and off when the lock opens", () => {
    const turn = load<TurnResponse>("turn_terms_consent");
    const card = turn.card as Extract<Card, { type: "consent_lock" }>;

    expect(card.data.acceptEnabled).toBe(true);
    expect(card.data.insurance.optional).toBe(true);
    expect(card.data.insurance.granted).toBe(false);
  });

  it("a wrong answer leaves consent locked", () => {
    const turn = load<TurnResponse>("turn_quiz_wrong");
    expect(turn.locks.acceptEnabled).toBe(false);

    const card = turn.card as Extract<Card, { type: "quiz" }>;
    expect(card.data.result?.correct).toBe(false);
    expect(card.data.result?.explanation).toBeTruthy();
  });

  it("the receipt points at the public check page", () => {
    const turn = load<TurnResponse>("turn_receipt");
    const card = turn.card as Extract<Card, { type: "receipt" }>;

    expect(card.data.receiptNo).toMatch(/^SP-/);
    expect(card.data.publicUrl).toContain("/r/");
    expect(card.data.insuranceTaken).toBe(false);
  });
});

describe("receipt verification fixtures", () => {
  it("a stored receipt verifies on all four checks", () => {
    const result = load<VerifyResult>("receipt_verify");

    expect(result.valid).toBe(true);
    expect(result.checks.map((check) => check.name)).toEqual([
      "payload_hash",
      "chain_link",
      "signature",
      "kfs_document",
    ]);
    expect(result.checks.every((check) => check.ok)).toBe(true);
  });

  it("an edited copy fails and names the field that changed", () => {
    const result = load<CandidateResult>("receipt_verify_candidate");

    expect(result.valid).toBe(false);
    expect(result.diff.length).toBeGreaterThan(0);
    expect(result.reasons.join(" ")).toContain("emi");

    const byName = Object.fromEntries(result.checks.map((check) => [check.name, check.ok]));
    expect(byName.payload_hash).toBe(false);
    expect(byName.signature).toBe(false);
  });

  it("the owner's view carries the masked payload and no full name", () => {
    const detail = load<ReceiptDetail>("receipt_detail");

    expect(detail.receiptNo).toMatch(/^SP-/);
    expect(detail.payload).toBeTruthy();
    // Masked only: a receipt never carries the persona's real name.
    expect(JSON.stringify(detail.payload)).not.toContain("Sunita Jadhav");
  });
});

describe("the consent_locked error", () => {
  it("decodes as the standard envelope", () => {
    const error = load<{ error: { code: string; message: string; requestId: string } }>(
      "error_consent_locked",
    );

    expect(error.error.code).toBe("consent_locked");
    expect(error.error.message.length).toBeGreaterThan(0);
  });
});
