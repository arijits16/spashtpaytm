import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, Sparkles, Upload } from "lucide-react";
import {
  apiBlob,
  getKfsDocument,
  getKfsLibrary,
  publishKfs,
  uploadKfs,
  verifyKfs,
} from "@/lib/api";
import type {
  GeneratedQuestion,
  KfsDocumentDetail,
  KfsDocumentRow,
  KfsLibraryResponse,
  KfsProposal,
} from "@/lib/types";
import { Card, ErrorNote, Pill, Spinner, Table } from "@/components/ui";
import { fmt } from "@/lib/format";

/**
 * The KFS library (build plan 12, phase 11).
 *
 * Upload a lender's Key Fact Statement, read its fields with Sarvam Document
 * Intelligence, **have a human verify them**, then publish: the offer is
 * re-priced from the verified facts and the generated teach-back questions go
 * live.
 *
 * The screen is built around the verification step rather than around the
 * upload, because that is where the responsibility sits. Every extracted field
 * shows its confidence next to the PDF it was read from, anything below the
 * threshold is amber, and the Publish button does not exist until a named
 * person has confirmed the figures.
 *
 * Publishing is two clicks on purpose. The first generates the questions and
 * explanation lines and runs them through the Number Guard; the second
 * activates what is on screen. No single action puts model-written text in
 * front of a customer.
 */
export function KfsLibrary() {
  const [library, setLibrary] = useState<KfsLibraryResponse | null>(null);
  const [selected, setSelected] = useState<KfsDocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (keep?: string) => {
    try {
      const next = await getKfsLibrary();
      setLibrary(next);
      setError(null);
      if (keep) setSelected(await getKfsDocument(keep));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the KFS library.");
    }
  }, []);

  // Deferred by a tick, like the other dashboard pages: a `setState` run
  // synchronously inside an effect body cascades a second render for nothing.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const run = useCallback(async (label: string, work: () => Promise<string | null>) => {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }, []);

  const open = useCallback(
    (documentId: string) =>
      void run("open", async () => {
        setSelected(await getKfsDocument(documentId));
        return null;
      }),
    [run],
  );

  if (!library) return <Spinner label="Loading the KFS library…" />;

  return (
    <div className="space-y-4 p-8">
      <header>
        <h1 className="text-text-1 text-2xl font-bold">KFS library</h1>
        <p className="text-text-3 mt-1 text-sm">
          Upload a lender&rsquo;s Key Fact Statement, check what was read out of it, and publish it
          once a human has verified the figures.
        </p>
      </header>

      {error && <ErrorNote message={error} onRetry={() => void load(selected?.documentId)} />}

      {notice && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
          <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" aria-hidden />
          <p className="text-[12.5px] text-emerald-900">{notice}</p>
        </div>
      )}

      <UploadCard
        library={library}
        busy={busy === "upload"}
        onUpload={(file, offerId, version) =>
          void run("upload", async () => {
            const detail = await uploadKfs(file, offerId, version);
            setSelected(detail);
            await load(detail.documentId);
            return `Read ${detail.fields.filter((f) => f.value !== null).length} fields and ${
              detail.clauseCount
            } clauses with ${detail.engine ?? "the offline reader"}. Verify them before publishing.`;
          })
        }
      />

      <Card
        title="Documents"
        subtitle="Newest first. Only an active document is quoted to a customer."
      >
        <Table
          headers={["Status", "Lender", "Offer", "Version", "Read by", "Verified by", "Uploaded"]}
          empty="No documents yet. `make seed` creates three; upload one above."
        >
          {library.documents.map((document) => (
            <DocumentRowView
              key={document.documentId}
              document={document}
              isSelected={selected?.documentId === document.documentId}
              onOpen={() => open(document.documentId)}
            />
          ))}
        </Table>
      </Card>

      {selected && (
        <DocumentDetailView
          // Keyed by the document, so selecting another one remounts the pane
          // and its half-typed corrections cannot be applied to the new one.
          key={selected.documentId}
          document={selected}
          busy={busy}
          onVerify={(corrections) =>
            void run("verify", async () => {
              const detail = await verifyKfs(selected.documentId, corrections);
              setSelected(detail);
              await load(detail.documentId);
              return `Verified by ${detail.verifiedBy}. You can generate the teach-back material now.`;
            })
          }
          onPropose={() =>
            void run("propose", async () => {
              const result = await publishKfs(selected.documentId, false);
              setSelected(await getKfsDocument(selected.documentId));
              return `Generated with ${result.engine}. Review the questions below, then activate.`;
            })
          }
          onActivate={() =>
            void run("activate", async () => {
              const result = await publishKfs(selected.documentId, true);
              await load(selected.documentId);
              return result.result
                ? `Activated ${result.result.version} for ${result.result.offerId}. The offer is re-priced at an EMI of ₹${fmt.rupees(
                    result.result.emi,
                  )} and an APR of ${result.result.apr}%. ${result.result.questions} questions are live.`
                : "Activated.";
            })
          }
        />
      )}
    </div>
  );
}

// --- upload ------------------------------------------------------------------

function UploadCard({
  library,
  busy,
  onUpload,
}: {
  library: KfsLibraryResponse;
  busy: boolean;
  onUpload: (file: File, offerId: string, version: string) => void;
}) {
  const [offerId, setOfferId] = useState(library.offers[0]?.offerId ?? "");
  const [version, setVersion] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const ready = file !== null && offerId !== "" && version.trim() !== "" && !busy;

  return (
    <Card
      title="Upload a Key Fact Statement"
      subtitle="PDF, 2 MB maximum. Admin only. Nothing it says reaches a customer until it is verified."
    >
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-text-3 text-[11px] font-semibold uppercase">Offer</span>
          <select
            value={offerId}
            onChange={(event) => setOfferId(event.target.value)}
            className="w-56 rounded-lg border border-slate-300 px-3 py-2 text-[13px]"
          >
            {library.offers.map((offer) => (
              <option key={offer.offerId} value={offer.offerId}>
                {offer.lender} ({offer.offerId}
                {offer.activeVersion ? ` · now ${offer.activeVersion}` : ""})
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-text-3 text-[11px] font-semibold uppercase">New version</span>
          <input
            value={version}
            onChange={(event) => setVersion(event.target.value)}
            placeholder="v4.0"
            maxLength={20}
            className="w-32 rounded-lg border border-slate-300 px-3 py-2 text-[13px]"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-text-3 text-[11px] font-semibold uppercase">File</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="text-text-2 w-72 text-[12px]"
          />
        </label>

        <button
          type="button"
          disabled={!ready}
          onClick={() => file && onUpload(file, offerId, version.trim())}
          className="bg-navy inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] font-bold text-white disabled:opacity-50"
        >
          <Upload size={14} aria-hidden />
          {busy ? "Reading the document…" : "Upload and extract"}
        </button>
      </div>
    </Card>
  );
}

// --- the list ----------------------------------------------------------------

const STATUS_TONE: Record<string, "good" | "info" | "warn" | "plain"> = {
  active: "good",
  verified: "info",
  draft: "warn",
  retired: "plain",
};

function DocumentRowView({
  document,
  isSelected,
  onOpen,
}: {
  document: KfsDocumentRow;
  isSelected: boolean;
  onOpen: () => void;
}) {
  return (
    <tr
      onClick={onOpen}
      className={`cursor-pointer border-b border-slate-100 last:border-0 ${
        isSelected ? "bg-slate-50" : ""
      }`}
    >
      <td className="px-2 py-2.5">
        <Pill tone={STATUS_TONE[document.status] ?? "plain"}>{document.status}</Pill>
      </td>
      <td className="text-text-1 px-2 py-2.5 text-[12.5px] font-semibold">{document.lender}</td>
      <td className="text-text-2 px-2 py-2.5 font-mono text-[11.5px]">{document.offerId ?? "—"}</td>
      <td className="text-text-2 px-2 py-2.5 font-mono text-[11.5px]">{document.version}</td>
      <td className="text-text-3 px-2 py-2.5 text-[11.5px]">{document.engine ?? "seed"}</td>
      <td className="text-text-3 px-2 py-2.5 text-[11.5px]">{document.verifiedBy ?? "—"}</td>
      <td className="text-text-3 px-2 py-2.5 text-[11.5px]">{fmt.dateTime(document.createdAt)}</td>
    </tr>
  );
}

// --- the detail pane ---------------------------------------------------------

function DocumentDetailView({
  document,
  busy,
  onVerify,
  onPropose,
  onActivate,
}: {
  document: KfsDocumentDetail;
  busy: string | null;
  onVerify: (corrections: Record<string, string>) => void;
  onPropose: () => void;
  onActivate: () => void;
}) {
  // Reset by the `key` on this component rather than by an effect: see the
  // call site.
  const [corrections, setCorrections] = useState<Record<string, string>>({});

  const lowCount = useMemo(() => document.fields.filter((field) => field.low).length, [document]);

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="space-y-4">
        <Card
          title={`Extracted fields · ${document.version}`}
          subtitle={`Read by ${document.engine ?? "the seed"}. ${
            lowCount > 0
              ? `${lowCount} below ${Math.round(document.lowConfidenceThreshold * 100)}% confidence.`
              : "Every scored field is above the confidence threshold."
          }`}
        >
          {document.sanityProblems.length > 0 && (
            <div className="mb-3 space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              {document.sanityProblems.map((problem) => (
                <p key={problem} className="flex items-start gap-1.5 text-[12px] text-amber-900">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden />
                  {problem}
                </p>
              ))}
            </div>
          )}

          <Table headers={["Field", "Read as", "Value", "Confidence", "Correct to"]} empty="">
            {document.fields.map((field) => (
              <tr key={field.key} className="border-b border-slate-100 last:border-0">
                <td className="text-text-2 px-2 py-1.5 font-mono text-[11px]">
                  {field.key}
                  {field.required && field.value === null && (
                    <span className="text-danger ml-1" title="Required">
                      *
                    </span>
                  )}
                </td>
                <td className="text-text-3 max-w-[150px] truncate px-2 py-1.5 text-[11px]">
                  {field.raw || "—"}
                </td>
                <td className="text-text-1 px-2 py-1.5 text-[12px] font-semibold">
                  {field.value === null ? (
                    <span className="text-danger">could not read</span>
                  ) : (
                    field.value
                  )}
                </td>
                <td className="px-2 py-1.5">
                  {field.confidence === null ? (
                    <span className="text-text-3 text-[11px]">unscored</span>
                  ) : (
                    <Pill tone={field.low ? "warn" : "good"}>
                      {Math.round(field.confidence * 100)}%
                    </Pill>
                  )}
                </td>
                <td className="px-2 py-1.5">
                  <input
                    value={corrections[field.key] ?? ""}
                    onChange={(event) =>
                      setCorrections((previous) => ({
                        ...previous,
                        [field.key]: event.target.value,
                      }))
                    }
                    placeholder="—"
                    className="w-20 rounded border border-slate-200 px-1.5 py-1 text-[11px]"
                  />
                </td>
              </tr>
            ))}
          </Table>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!document.canVerify || busy !== null}
              onClick={() =>
                onVerify(
                  Object.fromEntries(
                    Object.entries(corrections).filter(([, value]) => value.trim() !== ""),
                  ),
                )
              }
              className="bg-navy rounded-full px-4 py-2 text-[12.5px] font-bold text-white disabled:opacity-50"
            >
              {busy === "verify" ? "Verifying…" : "Verify these figures"}
            </button>

            {document.verifiedBy && (
              <p className="text-text-3 text-[11.5px]">
                Verified by <strong>{document.verifiedBy}</strong>
                {document.verifiedAt ? ` on ${fmt.dateTime(document.verifiedAt)}` : ""}
              </p>
            )}

            {document.missingRequired.length > 0 && (
              <p className="text-danger text-[11.5px]">
                Fill in: {document.missingRequired.join(", ")}
              </p>
            )}
          </div>

          <p className="text-text-3 mt-3 text-[11px]">
            SHA-256 <span className="font-mono">{document.sha256.slice(0, 24)}…</span> ·{" "}
            {document.clauseCount} clauses imported for KFS question answering
          </p>
        </Card>

        <PublishCard
          document={document}
          busy={busy}
          onPropose={onPropose}
          onActivate={onActivate}
        />
      </div>

      <PdfPreview
        key={document.fileUrl}
        url={document.fileUrl}
        label={`${document.lender} · ${document.version}`}
      />
    </div>
  );
}

// --- publish -----------------------------------------------------------------

function PublishCard({
  document,
  busy,
  onPropose,
  onActivate,
}: {
  document: KfsDocumentDetail;
  busy: string | null;
  onPropose: () => void;
  onActivate: () => void;
}) {
  const proposal: KfsProposal = document.generated ?? {};
  const questions = proposal.questions ?? [];

  return (
    <Card
      title="Teach-back material"
      subtitle="Generated from the verified facts, checked by the Number Guard, then reviewed here before it goes live."
    >
      {document.status === "draft" && (
        <p className="text-text-3 text-[12px]">
          Verify the figures first. Nothing is generated from an unverified document.
        </p>
      )}

      {document.canPublish && questions.length === 0 && (
        <button
          type="button"
          disabled={busy !== null}
          onClick={onPropose}
          className="bg-navy inline-flex items-center gap-2 rounded-full px-4 py-2 text-[12.5px] font-bold text-white disabled:opacity-50"
        >
          <Sparkles size={14} aria-hidden />
          {busy === "propose" ? "Generating…" : "Generate questions and lines"}
        </button>
      )}

      {questions.length > 0 && (
        <div className="space-y-3">
          <p className="text-text-3 text-[11.5px]">
            Written by <span className="font-mono">{proposal.engine ?? "seeded"}</span>. Figures are{" "}
            <span className="font-mono">{"{PLACEHOLDER}"}</span>s filled from the verified facts at
            render time, so no number here was written by the model.
          </p>

          {(proposal.blocked ?? []).length > 0 && (
            <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              {(proposal.blocked ?? []).map((line) => (
                <p key={line} className="text-[11.5px] text-amber-900">
                  {line}
                </p>
              ))}
            </div>
          )}

          {questions.map((question) => (
            <QuestionPreview key={question.factKey} question={question} />
          ))}

          {Object.entries(proposal.explain ?? {}).map(([key, block]) => (
            <div key={key} className="rounded-lg border border-slate-200 px-3 py-2">
              <p className="text-text-3 font-mono text-[10.5px]">{key}</p>
              <p className="text-text-1 text-[12px]">{block["mr-IN"]}</p>
            </div>
          ))}

          <button
            type="button"
            disabled={!document.canActivate || busy !== null}
            onClick={onActivate}
            className="rounded-full bg-emerald-600 px-4 py-2 text-[12.5px] font-bold text-white disabled:opacity-50"
          >
            {busy === "activate" ? "Activating…" : "Activate for new journeys"}
          </button>
          <p className="text-text-3 text-[11px]">
            Activating re-prices the offer from the verified facts, retires the previous document
            and replaces the active questions. `make seed` puts the seeded three back.
          </p>
        </div>
      )}
    </Card>
  );
}

function QuestionPreview({ question }: { question: GeneratedQuestion }) {
  return (
    <div className="rounded-lg border border-slate-200 px-3 py-2">
      <div className="mb-1 flex items-center gap-2">
        <Pill tone={question.origin === "generated" ? "info" : "plain"}>{question.origin}</Pill>
        <span className="text-text-3 font-mono text-[10.5px]">{question.factKey}</span>
      </div>
      <p className="text-text-1 text-[12.5px] font-semibold">{question.prompt["mr-IN"]}</p>
      <p className="text-text-3 text-[11.5px]">{question.prompt["en-IN"]}</p>
      <ul className="mt-1.5 space-y-0.5">
        {question.options.map((option) => (
          <li key={option.id} className="flex items-start gap-1.5 text-[11.5px]">
            {option.correct ? (
              <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-600" aria-hidden />
            ) : (
              <span className="mt-0.5 w-3 shrink-0" />
            )}
            <span className={option.correct ? "text-text-1" : "text-text-3"}>
              {option.text["en-IN"]}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- the PDF pane ------------------------------------------------------------

/**
 * The stored PDF, beside the fields that were read out of it.
 *
 * Fetched as a blob rather than pointed at with `<iframe src>`: the admin file
 * route needs the auth headers, which an iframe cannot send. The object URL is
 * revoked when the document changes, because a leaked one keeps the whole PDF
 * in memory for the life of the tab.
 */
function PdfPreview({ url, label }: { url: string; label: string }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  // Remounted per document by its `key`, so there is no stale state to clear.

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;

    const timer = setTimeout(() => {
      void (async () => {
        try {
          const blob = await apiBlob(url);
          if (cancelled) return;
          revoked = URL.createObjectURL(blob);
          setObjectUrl(revoked);
        } catch {
          if (!cancelled) setFailed(true);
        }
      })();
    }, 0);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      // Revoked on unmount: a leaked object URL keeps the whole PDF in memory
      // for the life of the tab.
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [url]);

  return (
    <Card title="The document" subtitle={label}>
      {failed ? (
        <p className="text-text-3 flex items-center gap-2 text-[12px]">
          <FileText size={14} aria-hidden />
          The stored file could not be opened.
        </p>
      ) : objectUrl === null ? (
        <Spinner label="Loading the PDF…" />
      ) : (
        <iframe
          src={objectUrl}
          title={`Key Fact Statement — ${label}`}
          className="h-[760px] w-full rounded-lg border border-slate-200"
        />
      )}
    </Card>
  );
}
