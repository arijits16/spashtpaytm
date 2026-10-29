import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { getHealth, type Health } from "@/lib/api";

/**
 * Phase-0 placeholder home.
 *
 * Its only job is to prove the whole chain works: browser -> Vite proxy ->
 * FastAPI -> Postgres. The real Paytm-style home screen replaces it in phase 3.
 */
export function HomePlaceholder() {
  const { data, isPending, isError, error } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: ({ signal }) => getHealth(signal),
    retry: 1,
  });

  return (
    <div className="px-screen flex min-h-full flex-col gap-cardgap py-6">
      <header>
        <div className="flex items-baseline gap-2">
          <span className="text-navy text-[26px] font-bold tracking-tight">Paytm</span>
          <span className="bg-badge-new text-text-1 rounded-full px-2 py-0.5 text-[10px] font-bold">
            Concept
          </span>
        </div>
        <p className="text-text-3 mt-1 text-caption">Spasht · loans you understand</p>
      </header>

      <section className="rounded-card bg-card p-cardpad">
        <h2 className="text-text-1 text-section font-bold">Phase 0 scaffold</h2>
        <p className="text-text-3 mt-1 text-body">Checking the backend through the Vite proxy.</p>

        <div className="mt-4 flex flex-col gap-2">
          {isPending && (
            <StatusRow state="pending" label="Backend" detail="contacting /api/health…" />
          )}

          {isError && (
            <StatusRow
              state="bad"
              label="Backend"
              detail={error instanceof Error ? error.message : "unreachable"}
            />
          )}

          {data && (
            <>
              <StatusRow state="good" label="Backend" detail="OK" />
              <StatusRow
                state={data.status === "ok" ? "good" : "bad"}
                label="DB"
                detail={data.db}
              />
              <StatusRow
                state={data.sarvam === "configured" ? "good" : "pending"}
                label="Sarvam"
                detail={data.sarvam === "configured" ? "configured" : "demo mode (no key yet)"}
              />
            </>
          )}
        </div>

        {data && (
          <p
            data-testid="health-summary"
            className="mt-4 border-t border-slate-100 pt-3 text-body font-semibold"
          >
            Backend: {data.status === "ok" ? "OK" : "DEGRADED"} · DB:{" "}
            {data.db === "ok" ? "OK" : "FAIL"}
            <span className="text-text-3 ml-2 text-caption font-normal">
              v{data.version} · {data.env}
            </span>
          </p>
        )}
      </section>

      <p className="text-text-3 mt-auto text-caption">
        The Paytm-style home screen, the profile drawer and the Spasht journey arrive in phases 3
        and 4.
      </p>
    </div>
  );
}

type RowState = "good" | "bad" | "pending";

const ROW_ICON = {
  good: <CheckCircle2 size={18} className="text-success" strokeWidth={2} aria-hidden />,
  bad: <XCircle size={18} className="text-danger" strokeWidth={2} aria-hidden />,
  pending: <Loader2 size={18} className="text-text-3 animate-spin" strokeWidth={2} aria-hidden />,
} satisfies Record<RowState, React.ReactNode>;

function StatusRow({ state, label, detail }: { state: RowState; label: string; detail: string }) {
  return (
    <div className="flex items-center gap-2.5">
      {ROW_ICON[state]}
      <span className="text-text-2 text-body font-semibold">{label}</span>
      <span className="text-text-3 text-body">{detail}</span>
    </div>
  );
}
