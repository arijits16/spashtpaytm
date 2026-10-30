import { useCallback } from "react";
import { ArrowDown } from "lucide-react";
import { getLedger } from "@/lib/api";
import { useLiveDashboard } from "@/lib/useLiveDashboard";
import type { LedgerResponse } from "@/lib/types";
import { Card, ConnectionBadge, ErrorNote, Pill, Skeleton } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The ledger view (build plan 12, 11.4).
 *
 * The last blocks as linked cards, each showing the previous hash it chains to,
 * plus today's Merkle anchor. The visible link is the explanation: you can see
 * that block 42's `prev` is block 41's `hash`, and therefore that changing 41
 * would break 42.
 */
export function Ledger() {
  const fetcher = useCallback((signal: AbortSignal) => getLedger(signal), []);
  const { data, error, loading, connection, refresh } = useLiveDashboard<LedgerResponse>({
    fetcher,
    events: ["receipt.created", "demo.reset"],
  });

  if (loading && !data) return <Skeleton rows={4} label="Walking the chain" />;

  return (
    <div className="space-y-4 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-text-1 text-2xl font-bold">Ledger</h1>
          <p className="text-text-3 mt-1 text-sm">
            Every receipt commits to the one before it. Altering one breaks all of the rest.
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {error && <ErrorNote message={error} onRetry={refresh} />}

      {data && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Card>
              <p className="text-text-3 text-[11px] font-medium tracking-wide uppercase">Chain</p>
              <div className="mt-2 flex items-center gap-2">
                <Pill tone={data.chainValid ? "good" : "bad"}>
                  {data.chainValid ? "Valid" : "Broken"}
                </Pill>
                <span className="text-text-2 text-[12.5px]">
                  {data.lastSeq} block{data.lastSeq === 1 ? "" : "s"}
                </span>
              </div>
              {data.problems.length > 0 && (
                <ul className="text-danger mt-2 space-y-0.5 text-[11.5px]">
                  {data.problems.map((problem) => (
                    <li key={problem}>· {problem}</li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="col-span-2">
              <p className="text-text-3 text-[11px] font-medium tracking-wide uppercase">
                Today&rsquo;s anchor
              </p>
              {data.todayAnchor ? (
                <>
                  <p className="text-text-1 mt-2 truncate font-mono text-[12px]">
                    {data.todayAnchor.merkleRoot}
                  </p>
                  <p className="text-text-3 mt-1 text-[11.5px]">
                    A SHA-256 Merkle root over today&rsquo;s {data.todayAnchor.receiptCount} receipt
                    {data.todayAnchor.receiptCount === 1 ? "" : "s"}. In production this would be
                    published somewhere we do not control, so that rewriting the whole chain would
                    no longer match a root the world already saw.
                  </p>
                </>
              ) : (
                <p className="text-text-3 mt-2 text-[12px]">
                  No receipts today, so there is nothing to anchor yet.
                </p>
              )}
            </Card>
          </div>

          <Card title="Recent blocks" subtitle="Newest first">
            {data.blocks.length === 0 ? (
              <p className="text-text-3 text-[12px]">
                The chain is empty. Complete a journey on the phone.
              </p>
            ) : (
              <ol className="space-y-0">
                {data.blocks.map((block, index) => (
                  <li key={block.seq}>
                    <div className="rounded-card border border-slate-200 p-4">
                      <div className="flex items-baseline justify-between">
                        <span className="text-text-1 font-mono text-[13px] font-bold">
                          #{block.seq} · {block.receiptNo}
                        </span>
                        <span className="text-text-3 text-[11px]">
                          {fmt.dateTime(block.createdAt)} · key {block.keyId}
                        </span>
                      </div>
                      <dl className="mt-2 space-y-1 text-[11px]">
                        <div className="flex gap-2">
                          <dt className="text-text-3 w-10">prev</dt>
                          <dd className="text-text-3 truncate font-mono" title={block.prevHash}>
                            {block.prevHash}
                          </dd>
                        </div>
                        <div className="flex gap-2">
                          <dt className="text-text-3 w-10">hash</dt>
                          <dd
                            className="text-navy truncate font-mono font-semibold"
                            title={block.hash}
                          >
                            {block.hash}
                          </dd>
                        </div>
                      </dl>
                    </div>
                    {index < data.blocks.length - 1 && (
                      <div className="flex justify-center py-1">
                        <ArrowDown size={14} className="text-text-3" aria-hidden />
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
