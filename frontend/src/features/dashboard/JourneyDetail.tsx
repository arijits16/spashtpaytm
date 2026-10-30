import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getJourneyDetail } from "@/lib/api";
import type { JourneyDetail } from "@/lib/types";
import { Card, ErrorNote, Pill, Spinner } from "@/components/ui";
import { fmt } from "@/lib/format";
import { StatusPill } from "@/features/dashboard/LiveJourneys";

/**
 * The journey detail drawer (build plan 12).
 *
 * Everything that happened, in one place: the audit timeline, the decrypted
 * transcript, every teach-back attempt including the wrong ones, and every
 * consent decision including the refusals.
 *
 * The attempts and consents matter most. They are the append-only evidence
 * (section 6), which is what lets this screen answer "did this person
 * understand what they agreed to?" rather than merely "did they tap agree?".
 */
export function JourneyDetailDrawer({
  journeyId,
  onClose,
}: {
  journeyId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<JourneyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      try {
        setDetail(await getJourneyDetail(journeyId, controller.signal));
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Could not load this journey.");
        }
      }
    })();

    return () => controller.abort();
  }, [journeyId]);

  // Escape closes the drawer. A modal panel with no keyboard exit is a trap.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button type="button" aria-label="Close" onClick={onClose} className="flex-1 bg-black/30" />

      <aside className="flex w-[680px] flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 flex items-start justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div>
            <h2 className="text-text-1 text-[17px] font-bold">
              {detail?.journey.personaName ?? "Journey"}
            </h2>
            <p className="text-text-3 mt-0.5 font-mono text-[11px]">{journeyId}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-text-3 hover:text-text-1 rounded p-1"
            aria-label="Close"
          >
            <X size={18} aria-hidden />
          </button>
        </header>

        <div className="space-y-4 p-6">
          {error && <ErrorNote message={error} />}
          {!detail && !error && <Spinner label="Loading the trail…" />}

          {detail && (
            <>
              <Card title="Journey">
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[12.5px]">
                  <Row label="Step" value={detail.journey.step} mono />
                  <Row label="Status" value={<StatusPill status={detail.journey.status} />} />
                  <Row label="Language" value={fmt.language(detail.journey.language)} />
                  <Row
                    label="Amount"
                    value={
                      detail.journey.amount === null ? "—" : `₹${fmt.rupees(detail.journey.amount)}`
                    }
                  />
                  <Row label="Offer" value={detail.journey.selectedOffer ?? "—"} />
                  <Row label="Duration" value={fmt.duration(detail.journey.durationSeconds)} />
                </dl>
              </Card>

              <Card
                title="Suitability"
                subtitle={
                  detail.suitability.incomeVerified
                    ? "Income verified from bank data"
                    : "Income self-declared — no bank data was shared"
                }
              >
                <div className="flex items-center gap-3">
                  <Pill tone={detail.suitability.decision === "suitable" ? "good" : "bad"}>
                    {detail.suitability.decision === "suitable" ? "Suitable" : "Not suitable"}
                  </Pill>
                  {detail.suitability.foir !== null && (
                    <span className="text-text-2 text-[12.5px]">
                      EMI is {fmt.percent(detail.suitability.foir * 100, 1)} of income
                    </span>
                  )}
                  {detail.suitability.monthlyIncome !== null && (
                    <span className="text-text-3 text-[12px]">
                      ₹{fmt.rupees(detail.suitability.monthlyIncome)}/month
                    </span>
                  )}
                </div>
                <ul className="text-text-2 mt-2 space-y-1 text-[12px]">
                  {detail.suitability.reasons.map((reason) => (
                    <li key={reason}>· {reason}</li>
                  ))}
                </ul>
              </Card>

              <Card
                title="Teach-back attempts"
                subtitle="Append-only, including the wrong answers — that is the point"
              >
                {detail.attempts.length === 0 ? (
                  <p className="text-text-3 text-[12px]">No attempts yet.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {detail.attempts.map((attempt) => (
                      <li
                        key={`${attempt.questionId}-${attempt.attemptNo}`}
                        className="flex items-center gap-2 text-[12.5px]"
                      >
                        <Pill tone={attempt.isCorrect ? "good" : "bad"}>
                          {attempt.isCorrect ? "correct" : "wrong"}
                        </Pill>
                        <span className="text-text-1 font-medium">{attempt.questionId}</span>
                        <span className="text-text-3">
                          attempt {attempt.attemptNo} · {attempt.answerType} · graded by{" "}
                          {attempt.grader}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card
                title="Consents"
                subtitle="Every decision, including refusals. The default column proves each toggle started off."
              >
                {detail.consents.length === 0 ? (
                  <p className="text-text-3 text-[12px]">No consents recorded yet.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {detail.consents.map((consent, index) => (
                      <li
                        key={`${consent.purpose}-${index}`}
                        className="flex items-center gap-2 text-[12.5px]"
                      >
                        <Pill tone={consent.granted ? "good" : "plain"}>
                          {consent.granted ? "granted" : "declined"}
                        </Pill>
                        <span className="text-text-1 font-medium">{consent.purpose}</span>
                        <span className="text-text-3">
                          via {consent.method} · default {consent.defaultValue ? "on" : "off"} ·{" "}
                          {fmt.time(consent.at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card
                title="Transcript"
                subtitle="Encrypted at rest (AES-256-GCM); decrypted here for an admin only"
              >
                {detail.transcript.length === 0 ? (
                  <p className="text-text-3 text-[12px]">Nothing recorded yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {detail.transcript.map((line) => (
                      <li key={line.turnNo} className="flex gap-2">
                        <span
                          className={`shrink-0 text-[10px] font-bold ${
                            line.role === "user" ? "text-navy" : "text-text-3"
                          }`}
                        >
                          {line.role === "user" ? "CUSTOMER" : "SPASHT"}
                        </span>
                        <div className="flex-1">
                          <p className="text-text-1 text-[12.5px]">{line.text}</p>
                          <p className="text-text-3 text-[10px]">
                            {line.source}
                            {line.sttMs !== null && ` · stt ${line.sttMs}ms`}
                            {line.llmMs !== null && ` · llm ${line.llmMs}ms`}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card title="Event timeline" subtitle="From the append-only audit log">
                <ol className="space-y-1">
                  {detail.timeline.map((event, index) => (
                    <li
                      key={`${event.at}-${index}`}
                      className="flex items-baseline gap-2 text-[12px]"
                    >
                      <span className="text-text-3 w-16 shrink-0 font-mono text-[10.5px]">
                        {fmt.time(event.at)}
                      </span>
                      <span className="text-text-1 font-medium">{event.eventType}</span>
                      {event.step && <span className="text-text-3 font-mono">{event.step}</span>}
                      <span className="text-text-3">{event.actor}</span>
                    </li>
                  ))}
                </ol>
              </Card>

              {detail.receiptNo && (
                <Card title="Receipt">
                  <a
                    href={`/dashboard/receipts/${detail.receiptNo}`}
                    className="text-navy font-mono text-[13px] font-bold underline"
                  >
                    {detail.receiptNo} →
                  </a>
                </Card>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-text-3">{label}</dt>
      <dd className={`text-text-1 font-semibold ${mono ? "font-mono text-[11.5px]" : ""}`}>
        {value}
      </dd>
    </>
  );
}
