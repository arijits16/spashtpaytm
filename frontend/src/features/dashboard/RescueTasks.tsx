import { useCallback } from "react";
import { getRescueTasks } from "@/lib/api";
import { useLiveDashboard } from "@/lib/useLiveDashboard";
import type { RescueRow } from "@/lib/types";
import { Card, ConnectionBadge, ErrorNote, Pill, Spinner, Table } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The rescue tasks page (build plan 12, phase 10).
 *
 * `contactWindowOk` is the column that matters. A task can exist while no call
 * is placed, and this says why: outside 9 am - 6 pm, or the persona is on DND,
 * or they never consented to callbacks. A rescue agent that cannot explain its
 * own silence is one nobody will trust to be quiet when it should be.
 */
export function RescueTasks() {
  const fetcher = useCallback((signal: AbortSignal) => getRescueTasks(signal), []);
  const { data, error, loading, connection, refresh } = useLiveDashboard<RescueRow[]>({
    fetcher,
    events: ["rescue.created", "journey.updated", "demo.reset"],
  });

  if (loading && !data) return <Spinner label="Loading rescue tasks…" />;

  return (
    <div className="space-y-4 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-text-1 text-2xl font-bold">Rescue tasks</h1>
          <p className="text-text-3 mt-1 text-sm">
            Journeys that stalled. A call is only placed inside the contact window, and never to
            someone on DND.
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {error && <ErrorNote message={error} onRetry={refresh} />}

      <Card>
        <Table
          headers={["Status", "Step", "Reason", "Contact window", "Created", "Journey"]}
          empty="No stalled journeys. Use Demo controls to create one."
        >
          {(data ?? []).map((task) => (
            <tr key={task.taskId} className="border-b border-slate-100 last:border-0">
              <td className="px-2 py-2.5">
                <Pill
                  tone={
                    task.status === "resumed"
                      ? "good"
                      : task.status === "ringing"
                        ? "info"
                        : task.status === "closed"
                          ? "plain"
                          : "warn"
                  }
                >
                  {task.status}
                </Pill>
              </td>
              <td className="text-text-2 px-2 py-2.5 font-mono text-[11.5px]">{task.step}</td>
              <td className="text-text-2 px-2 py-2.5">{task.reason}</td>
              <td className="px-2 py-2.5">
                {task.contactWindowOk ? (
                  <Pill tone="good">open</Pill>
                ) : (
                  <Pill tone="plain">closed — no call placed</Pill>
                )}
              </td>
              <td className="text-text-3 px-2 py-2.5">{fmt.dateTime(task.createdAt)}</td>
              <td className="text-text-3 px-2 py-2.5 font-mono text-[10.5px]">
                {task.journeyId.slice(0, 8)}…
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
