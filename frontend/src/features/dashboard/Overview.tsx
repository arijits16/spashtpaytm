import { useCallback } from "react";
import { getOverview } from "@/lib/api";
import { useLiveDashboard } from "@/lib/useLiveDashboard";
import type { FunnelStep, Overview as OverviewData, QuestionStat } from "@/lib/types";
import { Card, ConnectionBadge, ErrorNote, Kpi, Skeleton } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The compliance overview (build plan 12).
 *
 * The numbers are chosen to answer a compliance officer's questions, not a
 * growth team's. Each KPI carries a line saying what it means, because several
 * of them read backwards to anyone expecting an engagement dashboard: a **low**
 * insurance opt-in is the good outcome, and a guard that has blocked nothing is
 * a question rather than a clean bill of health.
 */
export function Overview() {
  const fetcher = useCallback((signal: AbortSignal) => getOverview(signal), []);
  const { data, error, loading, connection, refresh } = useLiveDashboard<OverviewData>({
    fetcher,
    events: ["journey.updated", "receipt.created", "guard.blocked", "demo.reset"],
  });

  if (loading && !data) return <Skeleton kpis={4} rows={5} label="Loading the overview" />;

  return (
    <div className="space-y-4 p-8">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-text-1 text-2xl font-bold">Overview</h1>
          <p className="text-text-3 mt-1 text-sm">
            Today, in Indian Standard Time. Synthetic data only.
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {error && <ErrorNote message={error} onRetry={refresh} />}

      {data && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <Kpi label="Journeys today" value={data.kpis.startedToday} />
            <Kpi
              label="Completed"
              value={data.kpis.completedToday}
              hint={`${fmt.percent(data.kpis.completionPct)} of those started`}
            />
            <Kpi
              label="Median time"
              value={fmt.duration(data.kpis.medianSecondsToComplete)}
              hint="Start to receipt"
            />
            <Kpi
              label="Live now"
              value={data.kpis.liveJourneys}
              tone={data.kpis.liveJourneys > 0 ? "good" : "plain"}
            />
          </div>

          <div className="grid grid-cols-4 gap-3">
            <Kpi
              label="Teach-back 1st try"
              value={fmt.percent(data.kpis.teachbackFirstAttemptPct)}
              hint="Understood without a re-explanation"
              tone={data.kpis.teachbackFirstAttemptPct >= 70 ? "good" : "warn"}
            />
            <Kpi
              label="Re-explanations"
              value={data.kpis.reexplanations}
              hint="Second and third attempts"
            />
            <Kpi
              label="Human handoffs"
              value={data.kpis.humanHandoffs}
              hint="People this could not help"
              tone={data.kpis.humanHandoffs > 0 ? "warn" : "plain"}
            />
            <Kpi
              label="Insurance opt-in"
              value={fmt.percent(data.kpis.insuranceOptInPct)}
              hint="Low is good — it means nothing is bundled"
              tone={data.kpis.insuranceOptInPct <= 20 ? "good" : "bad"}
            />
          </div>

          <div className="grid grid-cols-4 gap-3">
            <Kpi
              label="AI numbers blocked"
              value={data.kpis.guardBlocked}
              hint="Generated figures the Number Guard refused"
              tone={data.kpis.guardBlocked > 0 ? "warn" : "plain"}
            />
            <Kpi label="Receipts issued" value={data.kpis.receiptsTotal} />
            <div className="rounded-card col-span-2 border border-slate-200 bg-white p-4">
              <p className="text-text-3 text-[11px] font-medium tracking-wide uppercase">
                Language
              </p>
              <LanguageSplit split={data.kpis.languageSplit} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Card title="Funnel by step" subtitle="Journeys that reached each step today">
              <Funnel steps={data.funnel} />
            </Card>

            <Card
              title="First-attempt pass rate, per question"
              subtitle="A low rate here means the KFS wording needs work, not the customer"
            >
              <Questions questions={data.questions} />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function LanguageSplit({ split }: { split: Record<string, number> }) {
  const total = Object.values(split).reduce((sum, count) => sum + count, 0);
  if (total === 0) return <p className="text-text-3 mt-2 text-[12px]">No journeys yet today.</p>;

  const colours: Record<string, string> = {
    "mr-IN": "bg-navy",
    "hi-IN": "bg-sky",
    "en-IN": "bg-icon-line",
  };

  return (
    <div className="mt-3 space-y-2">
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
        {Object.entries(split).map(([code, count]) => (
          <div
            key={code}
            className={colours[code] ?? "bg-slate-400"}
            style={{ width: `${(100 * count) / total}%` }}
            title={`${fmt.language(code)}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {Object.entries(split).map(([code, count]) => (
          <span key={code} className="text-text-2 inline-flex items-center gap-1.5 text-[12px]">
            <span className={`h-2 w-2 rounded-full ${colours[code] ?? "bg-slate-400"}`} />
            {fmt.language(code)} · {count}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * The step funnel as horizontal bars.
 *
 * Bars rather than a chart library: a funnel is eleven labelled proportions,
 * and `div` widths render it exactly with no dependency, no bundle weight and
 * no axis to misread.
 */
function Funnel({ steps }: { steps: FunnelStep[] }) {
  const peak = Math.max(1, ...steps.map((step) => step.reached));

  return (
    <div className="space-y-1.5">
      {steps.map((step) => (
        <div key={step.step} className="flex items-center gap-3">
          <span className="text-text-3 w-24 shrink-0 text-right text-[11.5px]">{step.label}</span>
          <div className="h-5 flex-1 overflow-hidden rounded bg-slate-100">
            <div
              className="bg-navy flex h-full items-center justify-end rounded pr-2 transition-[width] duration-500"
              style={{ width: `${Math.max(2, (100 * step.reached) / peak)}%` }}
            >
              {step.reached > 0 && (
                <span className="text-[10px] font-bold text-white">{step.reached}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Questions({ questions }: { questions: QuestionStat[] }) {
  if (questions.length === 0) {
    return (
      <p className="text-text-3 text-[12px]">
        No teach-back attempts yet. Complete a journey on the phone and this fills in.
      </p>
    );
  }

  const labels: Record<string, string> = {
    q_late_fee: "What happens if an EMI is late",
    q_total_repay: "Total amount repayable",
    q_insurance_optional: "Insurance is optional",
    q_cooling_off: "Cooling-off period",
  };

  return (
    <div className="space-y-3">
      {questions.map((question) => {
        // Under half getting it right first time is a wording problem, and the
        // colour says so rather than leaving it to be read off a number.
        const tone =
          question.firstAttemptPct >= 70
            ? "bg-success"
            : question.firstAttemptPct >= 50
              ? "bg-warning"
              : "bg-danger";

        return (
          <div key={question.questionId}>
            <div className="mb-1 flex items-baseline justify-between">
              <span className="text-text-2 text-[12px] font-medium">
                {labels[question.questionId] ?? question.questionId}
              </span>
              <span className="text-text-1 text-[12px] font-bold">
                {fmt.percent(question.firstAttemptPct, 0)}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full transition-[width] duration-500 ${tone}`}
                style={{ width: `${question.firstAttemptPct}%` }}
              />
            </div>
            <p className="text-text-3 mt-1 text-[10.5px]">
              {question.attempts} attempt{question.attempts === 1 ? "" : "s"} ·{" "}
              {question.eventuallyPassed} eventually correct
            </p>
          </div>
        );
      })}
    </div>
  );
}
