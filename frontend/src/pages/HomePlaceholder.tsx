import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, LogOut, XCircle } from "lucide-react";
import { getHealth, type Health } from "@/lib/api";
import { useAuth } from "@/lib/authContext";

/**
 * Temporary signed-in home (build plan phase 1, step 5).
 *
 * Shows who is signed in, proves the browser -> Vite proxy -> FastAPI -> Postgres
 * chain still works, and offers Logout. The real Paytm-style home screen replaces
 * this in phase 3, and Logout moves into the profile drawer.
 */
export function HomePlaceholder() {
  const { me, isDemo, logout } = useAuth();
  const { data, isPending, isError, error } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: ({ signal }) => getHealth(signal),
    retry: 1,
  });

  return (
    <div className="px-screen flex min-h-full flex-col gap-cardgap py-6">
      <header className="flex items-start justify-between">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-navy text-[26px] font-bold tracking-tight">Paytm</span>
            <span className="bg-badge-new text-text-1 rounded-full px-2 py-0.5 text-[10px] font-bold">
              Concept
            </span>
          </div>
          <p className="text-text-3 mt-1 text-caption">Spasht · loans you understand</p>
        </div>
        <Avatar name={me?.displayName ?? null} photoUrl={me?.photoUrl ?? null} />
      </header>

      {/* --- who is signed in --- */}
      <section className="rounded-card bg-card p-cardpad">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-text-1 truncate text-section font-bold">
              {me?.displayName ?? "Signed in"}
            </p>
            <p className="text-text-3 truncate text-caption">{me?.email ?? "—"}</p>
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            className="text-text-2 flex shrink-0 items-center gap-1.5 rounded-full border border-slate-300 px-3 py-2 text-caption font-semibold"
          >
            <LogOut size={14} strokeWidth={2} aria-hidden />
            Logout
          </button>
        </div>

        <dl className="mt-4 flex flex-wrap gap-2">
          <Tag label="Language" value={me?.preferredLanguage ?? "—"} />
          <Tag label="Persona" value={me?.personaId ?? "—"} />
          <Tag label="Role" value={me?.isAdmin ? "admin" : "customer"} />
          {isDemo && <Tag label="Session" value="demo" tone="warn" />}
        </dl>

        {me?.isAdmin && (
          <a href="/dashboard" className="text-link mt-3 inline-block text-body font-semibold">
            Open the compliance dashboard →
          </a>
        )}
      </section>

      {/* --- backend health --- */}
      <section className="rounded-card bg-card p-cardpad">
        <h2 className="text-text-1 text-section font-bold">Phase 1 scaffold</h2>
        <p className="text-text-3 mt-1 text-body">
          Google sign-in works; the journey itself arrives in phase 4.
        </p>

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
        The Paytm-style home screen and the profile drawer arrive in phase 3; the Spasht journey in
        phase 4.
      </p>
    </div>
  );
}

/** Google photo when there is one, initials on the Paytm-ish green otherwise. */
function Avatar({ name, photoUrl }: { name: string | null; photoUrl: string | null }) {
  const initials = (name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");

  if (photoUrl) {
    return (
      <img
        src={photoUrl}
        alt=""
        referrerPolicy="no-referrer"
        className="size-11 shrink-0 rounded-full object-cover"
      />
    );
  }
  return (
    <span
      aria-hidden
      className="text-text-1 flex size-11 shrink-0 items-center justify-center rounded-full bg-[#D9E8C4] text-body font-bold"
    >
      {initials}
    </span>
  );
}

function Tag({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div
      className={[
        "rounded-full px-2.5 py-1 text-[11px]",
        tone === "warn" ? "bg-badge-new text-text-1 font-semibold" : "text-text-2 bg-slate-100",
      ].join(" ")}
    >
      <span className="text-text-3">{label}: </span>
      {value}
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
