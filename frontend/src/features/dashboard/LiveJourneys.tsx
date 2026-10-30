import { useCallback, useState } from "react";
import { getJourneys } from "@/lib/api";
import { useLiveDashboard } from "@/lib/useLiveDashboard";
import type { JourneyRow } from "@/lib/types";
import { Card, ConnectionBadge, ErrorNote, LiveDot, Pill, Spinner, Table } from "@/components/ui";
import { fmt } from "@/lib/format";
import { JourneyDetailDrawer } from "@/features/dashboard/JourneyDetail";

/**
 * The live journeys table (build plan 12).
 *
 * Updated over SSE, so finishing a journey on the phone shows here within two
 * seconds without a refresh - the phase-9 acceptance criterion.
 *
 * Names are the masked persona names. The dashboard never shows an unmasked
 * field, even to an admin, except the decrypted transcript in the drawer.
 */
export function LiveJourneys() {
  const fetcher = useCallback((signal: AbortSignal) => getJourneys(signal), []);
  const { data, error, loading, connection, refresh } = useLiveDashboard<JourneyRow[]>({
    fetcher,
    events: ["journey.updated", "receipt.created", "demo.reset"],
  });

  const [selected, setSelected] = useState<string | null>(null);

  if (loading && !data) return <Spinner label="Loading journeys…" />;

  return (
    <div className="space-y-4 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-text-1 text-2xl font-bold">Live journeys</h1>
          <p className="text-text-3 mt-1 text-sm">
            Most recent activity first. Click a row for the full trail.
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {error && <ErrorNote message={error} onRetry={refresh} />}

      <Card>
        <Table
          headers={[
            "",
            "Customer",
            "Language",
            "Step",
            "Status",
            "Amount",
            "Offer",
            "Duration",
            "Last activity",
            "Receipt",
          ]}
          empty="No journeys yet. Start one on the phone, or use Demo controls."
        >
          {(data ?? []).map((row) => (
            <tr
              key={row.journeyId}
              onClick={() => setSelected(row.journeyId)}
              className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
            >
              <td className="px-2 py-2.5">
                <LiveDot live={row.isLive} />
              </td>
              <td className="text-text-1 px-2 py-2.5 font-semibold">
                {row.personaName ?? row.personaId ?? "—"}
              </td>
              <td className="text-text-2 px-2 py-2.5">{fmt.language(row.language)}</td>
              <td className="text-text-2 px-2 py-2.5 font-mono text-[11.5px]">{row.step}</td>
              <td className="px-2 py-2.5">
                <StatusPill status={row.status} />
              </td>
              <td className="text-text-2 px-2 py-2.5">
                {row.amount === null ? "—" : `₹${fmt.rupees(row.amount)}`}
              </td>
              <td className="text-text-3 px-2 py-2.5">{row.selectedOffer ?? "—"}</td>
              <td className="text-text-2 px-2 py-2.5">{fmt.duration(row.durationSeconds)}</td>
              <td className="text-text-3 px-2 py-2.5">
                {fmt.duration(row.lastActivitySeconds)} ago
              </td>
              <td className="px-2 py-2.5">
                {row.receiptNo ? (
                  <span className="text-navy font-mono text-[11px] font-semibold">
                    {row.receiptNo}
                  </span>
                ) : (
                  <span className="text-text-3">—</span>
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {selected && <JourneyDetailDrawer journeyId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const config: Record<
    string,
    { label: string; tone: "good" | "warn" | "bad" | "info" | "plain" }
  > = {
    active: { label: "Active", tone: "info" },
    completed: { label: "Completed", tone: "good" },
    // A handoff is not a failure of the customer, so it reads as "needs a
    // person" rather than as an error.
    needs_human: { label: "Needs a person", tone: "warn" },
    abandoned: { label: "Abandoned", tone: "plain" },
  };

  const entry = config[status] ?? { label: status, tone: "plain" as const };
  return <Pill tone={entry.tone}>{entry.label}</Pill>;
}
