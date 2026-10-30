import { useCallback, useEffect, useState } from "react";
import { PhoneCall, RotateCcw, UserCog } from "lucide-react";
import { createAbandonedJourney, getPersonas, resetDemo, switchPersona } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import { DEMO_AUTH_ENABLED } from "@/lib/env";
import { Card, ErrorNote, Pill } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The demo controls (build plan 12, dev only).
 *
 * The backend refuses all of these outside `APP_ENV=dev` whatever this page
 * shows (section 13.9), because the reset truncates the evidence tables - the
 * one operation the append-only triggers exist to prevent. This page is the
 * convenience; the environment check is the control.
 */
interface Persona {
  id: string;
  displayNameMasked: string;
  language: string;
  city: string;
  occupation: string;
}

export function DemoControls() {
  const { me, refreshMe } = useAuth();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getPersonas(controller.signal)
      .then(setPersonas)
      .catch(() => {
        /* Not fatal: the other controls still work without the list. */
      });
    return () => controller.abort();
  }, []);

  const run = useCallback(async (name: string, action: () => Promise<string>) => {
    setBusy(name);
    setError(null);
    setMessage(null);
    try {
      setMessage(await action());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }, []);

  return (
    <div className="space-y-4 p-8">
      <header>
        <h1 className="text-text-1 text-2xl font-bold">Demo controls</h1>
        <p className="text-text-3 mt-1 text-sm">
          Dev only. The backend refuses these outside a dev environment regardless of what this page
          offers.
        </p>
      </header>

      {!DEMO_AUTH_ENABLED && (
        <ErrorNote message="VITE_DEMO_AUTH is off, so this build is not configured for demo use. The controls may still work if you are signed in as a real admin in dev." />
      )}

      {error && <ErrorNote message={error} />}
      {message && (
        <div className="rounded-card border border-success/30 bg-success/8 px-4 py-3">
          <p className="text-success text-[12.5px] font-semibold">{message}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Card
          title="Reset the demo"
          subtitle="Clears every journey, receipt and event; resets the ledger to genesis; re-seeds the catalogue."
        >
          <p className="text-text-3 mb-3 text-[12px]">
            Personas, offers, KFS documents and the question bank are kept. Run this between
            rehearsals so the funnel starts clean.
          </p>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              void run("reset", async () => {
                const result = await resetDemo();
                const counts = Object.entries(result.counts)
                  .map(([group, count]) => `${group} ${count}`)
                  .join(", ");
                return `Reset. Re-seeded: ${counts}.`;
              })
            }
            className="bg-danger inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] font-bold text-white disabled:opacity-50"
          >
            <RotateCcw size={14} aria-hidden />
            {busy === "reset" ? "Resetting…" : "Reset demo data"}
          </button>
        </Card>

        <Card
          title="Create an abandoned journey"
          subtitle="So the rescue agent has something to find (phase 10)."
        >
          <p className="text-text-3 mb-3 text-[12px]">
            Creates a journey for the demo customer, stalled at the offers screen and idle for three
            minutes. Within about 30 seconds the phone should ring.
          </p>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              void run("abandoned", async () => {
                const result = await createAbandonedJourney({
                  personaId: "sunita",
                  step: "OFFERS",
                  idleSeconds: 180,
                });
                return `Created a journey stalled at ${result.step}. Watch the phone.`;
              })
            }
            className="bg-navy inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] font-bold text-white disabled:opacity-50"
          >
            <PhoneCall size={14} aria-hidden />
            {busy === "abandoned" ? "Creating…" : "Create abandoned journey"}
          </button>
        </Card>
      </div>

      <Card
        title="Switch persona"
        subtitle="Which synthetic customer the next journey is linked to."
        actions={me?.persona ? <Pill tone="info">now: {me.persona.id}</Pill> : undefined}
      >
        <div className="grid grid-cols-3 gap-3">
          {personas.map((persona) => {
            const current = me?.persona?.id === persona.id;
            return (
              <button
                key={persona.id}
                type="button"
                disabled={busy !== null || current}
                onClick={() =>
                  void run("persona", async () => {
                    await switchPersona(persona.id);
                    await refreshMe();
                    return `Linked to ${persona.displayNameMasked}.`;
                  })
                }
                className={`rounded-card border p-4 text-left transition-colors ${
                  current
                    ? "border-navy bg-offer-strip/40"
                    : "border-slate-200 hover:border-slate-300"
                } disabled:opacity-70`}
              >
                <div className="flex items-center gap-2">
                  <UserCog size={14} className="text-navy" aria-hidden />
                  <span className="text-text-1 text-[13px] font-bold">
                    {persona.displayNameMasked}
                  </span>
                </div>
                <p className="text-text-3 mt-1 text-[11.5px]">
                  {persona.occupation}, {persona.city}
                </p>
                <p className="text-text-2 mt-0.5 text-[11.5px]">{fmt.language(persona.language)}</p>
              </button>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
