import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { Check, RotateCcw, X } from "lucide-react";
import { getReceipt, verifyCandidate, verifyReceipt } from "@/lib/api";
import type {
  CandidateResult,
  Check as CheckResult,
  ReceiptDetail,
  VerifyResult,
} from "@/lib/types";
import { Card, ErrorNote, Pill, Spinner } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The receipt check page and the tamper editor (build plan 11.3, 5.8).
 *
 * This is the page that makes the trust layer legible to someone who does not
 * want to read about hash chains. Four checks, green. Then you edit the EMI in
 * the browser, press verify, and it goes red and names the field you changed -
 * while the stored receipt stays green, because the editor never writes
 * anything.
 *
 * That last part is the point, and it is why there is a second "re-check the
 * stored receipt" button: the demo is only convincing if you can see that the
 * real one survived.
 */
export function ReceiptCheck() {
  const { receiptNo = "" } = useParams();

  const [receipt, setReceipt] = useState<ReceiptDetail | null>(null);
  const [stored, setStored] = useState<VerifyResult | null>(null);
  const [candidate, setCandidate] = useState<CandidateResult | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [detail, verification] = await Promise.all([
        getReceipt(receiptNo),
        verifyReceipt(receiptNo),
      ]);
      setReceipt(detail);
      setStored(verification);
      setDraft(JSON.stringify(detail.payload, null, 2));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load this receipt.");
    }
  }, [receiptNo]);

  // The lint rule rightly objects to a synchronous setState in an effect body;
  // this is an async fetch whose result lands in a later tick, which is the
  // sanctioned "subscribe to an external system" shape.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      setCandidate(await verifyCandidate(receiptNo, parsePayload(draft)));
      // Re-read the stored receipt immediately afterwards, so the page can
      // show that editing a copy changed nothing.
      setStored(await verifyReceipt(receiptNo));
    } catch (cause) {
      setError(
        cause instanceof SyntaxError
          ? "That is not valid JSON. Edit a value, not the structure."
          : cause instanceof Error
            ? cause.message
            : "Could not verify that copy.",
      );
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    if (receipt) setDraft(JSON.stringify(receipt.payload, null, 2));
    setCandidate(null);
    setError(null);
  };

  /** Edit one figure, so the demo needs no JSON typing on stage. */
  const tamperEmi = () => {
    if (!receipt) return;
    const copy = structuredClone(receipt.payload);
    const terms = copy.terms;
    if (isRecord(terms) && typeof terms.emi === "number") {
      terms.emi = 4000;
    }
    setDraft(JSON.stringify(copy, null, 2));
  };

  if (!receipt && !error) return <Spinner label="Loading the receipt…" />;

  return (
    <div className="space-y-4 p-8">
      <header>
        <Link to="/dashboard/receipts" className="text-text-3 text-[12px]">
          ← Receipts
        </Link>
        <h1 className="text-text-1 mt-1 font-mono text-2xl font-bold">{receiptNo}</h1>
        {receipt && (
          <p className="text-text-3 mt-1 text-sm">
            {receipt.lender} · block #{receipt.seq} · {fmt.dateTime(receipt.createdAt)} · understood{" "}
            {receipt.teachbackPassed}/{receipt.teachbackTotal}
          </p>
        )}
      </header>

      {error && <ErrorNote message={error} onRetry={() => void load()} />}

      <div className="grid grid-cols-2 gap-4">
        <Card
          title="The stored receipt"
          subtitle="The four checks of section 11.3, run against the database"
          actions={
            stored && (
              <Pill tone={stored.valid ? "good" : "bad"}>
                {stored.valid ? "Verified" : "Not verified"}
              </Pill>
            )
          }
        >
          {stored ? <Checks checks={stored.checks} /> : <Spinner />}
          {stored && (
            <dl className="mt-4 space-y-1 border-t border-slate-100 pt-3 text-[11.5px]">
              <HashRow label="hash" value={stored.hash} />
              <HashRow label="prev" value={stored.prevHash} />
              <div className="flex gap-2">
                <dt className="text-text-3 w-12">key</dt>
                <dd className="text-text-2 font-mono">{stored.keyId}</dd>
              </div>
            </dl>
          )}
        </Card>

        <Card
          title="Simulate tampering"
          subtitle="Edit a value and verify the copy. The database is never written to."
          actions={
            candidate && (
              <Pill tone={candidate.valid ? "good" : "bad"}>
                {candidate.valid ? "Still valid" : "TAMPERED"}
              </Pill>
            )
          }
        >
          <div className="mb-2 flex gap-2">
            <button
              type="button"
              onClick={tamperEmi}
              className="rounded-full bg-slate-100 px-3 py-1.5 text-[11.5px] font-semibold text-text-2 hover:bg-slate-200"
            >
              Change the EMI to ₹4,000
            </button>
            <button
              type="button"
              onClick={reset}
              className="text-text-3 inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[11.5px] font-semibold hover:bg-slate-100"
            >
              <RotateCcw size={11} aria-hidden />
              Reset
            </button>
          </div>

          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
            className="h-72 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-[11px] leading-relaxed"
            aria-label="Receipt payload, editable"
          />

          <button
            type="button"
            onClick={() => void check()}
            disabled={busy}
            className="bg-navy mt-2 w-full rounded-full py-2.5 text-[13px] font-bold text-white disabled:opacity-50"
          >
            {busy ? "Verifying…" : "Verify this copy"}
          </button>

          {candidate && (
            <div className="mt-4 space-y-3">
              <Checks checks={candidate.checks} />

              {candidate.reasons.length > 0 && (
                <div className="bg-alert-pink rounded-lg px-3 py-2.5">
                  <p className="text-danger text-[11px] font-bold tracking-wide uppercase">
                    What changed
                  </p>
                  <ul className="text-text-2 mt-1 space-y-0.5 font-mono text-[11.5px]">
                    {candidate.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}

              {!candidate.valid && (
                <p className="text-text-3 text-[11.5px]">
                  The edited copy no longer hashes to the signed hash, so the signature over that
                  hash no longer stands. The stored receipt on the left is unchanged.
                </p>
              )}
            </div>
          )}
        </Card>
      </div>

      {receipt && (
        <Card title="Payload" subtitle="Masked fields only. No full name, no account number.">
          <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 font-mono text-[11px] leading-relaxed">
            {JSON.stringify(receipt.payload, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Parse the edited payload.
 *
 * `JSON.parse` returns `any`, so the shape is checked rather than asserted: the
 * textarea is free-form, and posting a bare array or a string to
 * `verify-candidate` would be a confusing 422 instead of a clear message here.
 */
function parsePayload(draft: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(draft);
  if (!isRecord(parsed)) {
    throw new SyntaxError("The payload must be a JSON object.");
  }
  return parsed;
}

function Checks({ checks }: { checks: CheckResult[] }) {
  return (
    <ul className="space-y-2">
      {checks.map((check) => (
        <li key={check.name} className="flex items-start gap-2.5">
          {check.ok ? (
            <Check size={15} className="text-success mt-0.5 shrink-0" aria-hidden />
          ) : (
            <X size={15} className="text-danger mt-0.5 shrink-0" aria-hidden />
          )}
          <div>
            <p className="text-text-1 text-[12.5px] font-semibold">
              {check.name.replace(/_/g, " ")}
            </p>
            <p className="text-text-3 text-[11.5px]">{check.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-text-3 w-12">{label}</dt>
      <dd className="text-text-2 truncate font-mono" title={value}>
        {value}
      </dd>
    </div>
  );
}
