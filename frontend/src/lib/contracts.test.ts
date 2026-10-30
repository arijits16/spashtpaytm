import { describe, expect, it } from "vitest";
import errorNotFound from "../../../contracts/fixtures/error_not_found.json";
import errorUnauthorized from "../../../contracts/fixtures/error_unauthorized.json";
import healthFixture from "../../../contracts/fixtures/health.json";
import meFixture from "../../../contracts/fixtures/me.json";
import type { Health, Me } from "@/lib/api";

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
