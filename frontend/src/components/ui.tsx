import type { ReactNode } from "react";
import { AlertTriangle, Loader2, Radio, RefreshCw } from "lucide-react";
import type { ConnectionState } from "@/lib/sse";

/**
 * The dashboard's shared primitives (build plan 5.8, 12).
 *
 * Small and unopinionated: the pages carry the meaning, these carry the look.
 */

/** A white card. The dashboard's only container. */
export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-card border border-slate-200 bg-white ${className}`}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div>
            {title && <h2 className="text-text-1 text-[15px] font-bold">{title}</h2>}
            {subtitle && <p className="text-text-3 mt-0.5 text-[12px]">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

/**
 * One KPI.
 *
 * `hint` is where the number's *meaning* goes, which matters more here than on
 * a typical dashboard: "insurance opt-in 0%" looks like a dead feature until it
 * says that a low number is the point (section 12).
 */
export function Kpi({
  label,
  value,
  hint,
  tone = "plain",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "plain" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    plain: "text-text-1",
    good: "text-success",
    warn: "text-warning",
    bad: "text-danger",
  }[tone];

  return (
    <div className="rounded-card border border-slate-200 bg-white p-4">
      <p className="text-text-3 text-[11px] font-medium tracking-wide uppercase">{label}</p>
      <p className={`mt-1.5 text-[26px] leading-none font-bold ${toneClass}`}>{value}</p>
      {hint && <p className="text-text-3 mt-1.5 text-[11px] leading-snug">{hint}</p>}
    </div>
  );
}

/** A table that scrolls horizontally rather than squashing its columns. */
export function Table({
  headers,
  children,
  empty,
}: {
  headers: string[];
  children: ReactNode;
  empty?: string;
}) {
  const hasRows = Array.isArray(children) ? children.length > 0 : Boolean(children);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-slate-200">
            {headers.map((header) => (
              <th
                key={header}
                className="text-text-3 px-2 py-2 text-[10.5px] font-semibold tracking-wide whitespace-nowrap uppercase"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
      {!hasRows && (
        <p className="text-text-3 py-6 text-center text-[12px]">{empty ?? "Nothing yet."}</p>
      )}
    </div>
  );
}

/** A status pill. */
export function Pill({
  children,
  tone = "plain",
}: {
  children: ReactNode;
  tone?: "plain" | "good" | "warn" | "bad" | "info";
}) {
  const toneClass = {
    plain: "bg-slate-100 text-text-2",
    good: "bg-success/12 text-success",
    warn: "bg-warning/15 text-warning",
    bad: "bg-danger/12 text-danger",
    info: "bg-offer-strip text-navy",
  }[tone];

  return (
    <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${toneClass}`}>
      {children}
    </span>
  );
}

/** The pulsing dot on an active journey (section 12). */
export function LiveDot({ live }: { live: boolean }) {
  if (!live) return <span className="inline-block h-2 w-2 rounded-full bg-slate-300" />;
  return (
    <span className="relative inline-flex h-2 w-2">
      <span className="bg-success absolute inline-flex h-full w-full animate-ping rounded-full opacity-70" />
      <span className="bg-success relative inline-flex h-2 w-2 rounded-full" />
    </span>
  );
}

/**
 * Whether the live feed is connected.
 *
 * Shown rather than hidden, because "polling" is a real state the operator
 * should be able to see: a dashboard that silently stopped streaming looks
 * identical to one where nothing is happening.
 */
export function ConnectionBadge({ state }: { state: ConnectionState }) {
  const config = {
    connecting: { label: "Connecting…", tone: "plain" as const },
    live: { label: "Live", tone: "good" as const },
    polling: { label: "Polling", tone: "warn" as const },
  }[state];

  return (
    <span className="inline-flex items-center gap-1.5">
      <Radio size={11} aria-hidden />
      <Pill tone={config.tone}>{config.label}</Pill>
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10" role="status" aria-live="polite">
      <Loader2 size={18} className="text-navy animate-spin" aria-hidden />
      {label && <p className="text-text-3 text-[12.5px]">{label}</p>}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="bg-alert-pink rounded-card flex items-start gap-3 px-4 py-3">
      <AlertTriangle size={16} className="text-danger mt-0.5 shrink-0" aria-hidden />
      <p className="text-text-2 flex-1 text-[12.5px]">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-navy inline-flex items-center gap-1 text-[12px] font-bold"
        >
          <RefreshCw size={12} aria-hidden />
          Retry
        </button>
      )}
    </div>
  );
}
