import { useCallback } from "react";
import { Link } from "react-router";
import { getDashboardReceipts } from "@/lib/api";
import { useLiveDashboard } from "@/lib/useLiveDashboard";
import type { ReceiptRow } from "@/lib/types";
import { Card, ConnectionBadge, ErrorNote, Skeleton, Table } from "@/components/ui";
import { fmt } from "@/lib/format";

/** The receipts table (build plan 12). Each row links to its check page. */
export function Receipts() {
  const fetcher = useCallback((signal: AbortSignal) => getDashboardReceipts(signal), []);
  const { data, error, loading, connection, refresh } = useLiveDashboard<ReceiptRow[]>({
    fetcher,
    events: ["receipt.created", "demo.reset"],
  });

  if (loading && !data) return <Skeleton rows={6} label="Loading receipts" />;

  return (
    <div className="space-y-4 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-text-1 text-2xl font-bold">Receipts</h1>
          <p className="text-text-3 mt-1 text-sm">
            Hash-chained and Ed25519-signed. Open one to check it, or to simulate tampering.
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {error && <ErrorNote message={error} onRetry={refresh} />}

      <Card>
        <Table
          headers={["Seq", "Receipt", "Lender", "Language", "Hash", "Issued", ""]}
          empty="No receipts yet. Complete a journey on the phone."
        >
          {(data ?? []).map((row) => (
            <tr key={row.receiptNo} className="border-b border-slate-100 last:border-0">
              <td className="text-text-3 px-2 py-2.5 font-mono">#{row.seq}</td>
              <td className="text-text-1 px-2 py-2.5 font-mono font-semibold">{row.receiptNo}</td>
              <td className="text-text-2 px-2 py-2.5">{row.lender}</td>
              <td className="text-text-2 px-2 py-2.5">{fmt.language(row.language)}</td>
              <td className="text-text-3 px-2 py-2.5 font-mono text-[11px]">
                {fmt.hash(row.shortHash)}
              </td>
              <td className="text-text-3 px-2 py-2.5">{fmt.dateTime(row.createdAt)}</td>
              <td className="px-2 py-2.5 text-right">
                <Link
                  to={`/dashboard/receipts/${row.receiptNo}`}
                  className="text-navy text-[12px] font-bold"
                >
                  Check →
                </Link>
              </td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
