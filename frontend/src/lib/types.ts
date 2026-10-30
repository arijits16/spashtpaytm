/**
 * The API contract, as TypeScript (build plan 8.3-8.4).
 *
 * Mirrors `backend/app/journey/responses.py` and `cards.py`, and the
 * `contracts/fixtures/*.json` that `contracts.test.ts` decodes. A backend field
 * rename fails `npm run build` rather than the demo.
 *
 * The website is the **dashboard**, so it renders cards only on the receipt
 * check page - but the card types are declared in full, because the journey
 * detail drawer shows what the customer was shown and the fixture tests decode
 * every one of them.
 */

export type Lang = "mr-IN" | "hi-IN" | "en-IN";

export type Step =
  | "INTRO"
  | "ASK_NEED"
  | "CONSENT_DATA"
  | "MANUAL_FORM"
  | "PREFILL"
  | "CONFIRM_DETAILS"
  | "OFFERS"
  | "EXPLAIN_KFS"
  | "TEACHBACK"
  | "TERMS_CONSENT"
  | "OTP"
  | "RECEIPT"
  | "DONE"
  | "HUMAN_HANDOFF";

// --- cards -------------------------------------------------------------------

export interface OfferSummary {
  offerId: string;
  lender: string;
  lenderType: "NBFC" | "Bank";
  principal: number;
  tenureMonths: number;
  ratePa: number;
  processingFee: number;
  gst: number;
  /** The figure the comparison is sorted by and shown in bold. */
  apr: number;
  emi: number;
  totalRepay: number;
  /** Interest + fee + GST: what the customer loses. */
  totalCost: number;
  badges: ("lowest_total_cost" | "low_rate_high_fee")[];
  kfsUrl: string;
}

export interface Suitability {
  /** A percentage (16.4), not a fraction. */
  foirPct: number;
  decision: "suitable" | "not_suitable";
  reasons: string[];
}

export interface QuizCardData {
  questionId: string;
  index: number;
  total: number;
  prompt: string;
  options: { id: string; text: string }[];
  attempt: number;
  maxAttempts: number;
  result?: { correct: boolean; explanation?: string | null } | null;
}

export interface ReceiptCardData {
  receiptNo: string;
  lender: string;
  emi: number;
  tenureMonths: number;
  totalRepay: number;
  language: Lang;
  teachback: { passed: number; total: number };
  insuranceTaken: boolean;
  publicUrl: string;
  summaryText: string;
  createdAt: string;
}

/**
 * The card union, discriminated on `type`.
 *
 * An unknown `type` is deliberately representable: the website must render what
 * it understands and ignore the rest, exactly as the app decodes unknown cards
 * to `.unsupported` rather than failing.
 */
export type Card =
  | { type: "language"; data: { options: { language: Lang; label: string }[] } }
  | { type: "amount"; data: { chips: number[]; min: number; max: number } }
  | {
      type: "consent";
      data: {
        purposes: { id: string; title: string; detail: string; granted: boolean }[];
        why: string;
      };
    }
  | {
      type: "manual_form";
      data: { fields: { id: string; label: string; kind: string; required: boolean }[] };
    }
  | { type: "prefill"; data: { rows: { label: string; value: string; source: string }[] } }
  | { type: "confirm"; data: { fields: { id: string; label: string; value: string }[] } }
  | { type: "offers"; data: { suitability: Suitability; offers: OfferSummary[] } }
  | {
      type: "kfs";
      data: {
        offerId: string;
        lender: string;
        version: string;
        lines: { key: string; text: string; redFlag: boolean }[];
        pdfUrl: string;
        sample: boolean;
      };
    }
  | { type: "quiz"; data: QuizCardData }
  | {
      type: "consent_lock";
      data: {
        acceptEnabled: boolean;
        reason?: string | null;
        terms: string[];
        insurance: { premium: number; granted: boolean; optional: boolean };
      };
    }
  | {
      type: "otp";
      data: {
        length: number;
        expiresInSec: number;
        attemptsLeft: number;
        demoCode?: string | null;
      };
    }
  | { type: "receipt"; data: ReceiptCardData }
  | { type: "handoff"; data: { message: string; window: string } }
  /**
   * A card type this build does not know.
   *
   * `UnknownCard` rather than `{type: string}`: a bare `string` member absorbs
   * every literal above it and TypeScript stops narrowing the union at all, so
   * `switch (card.type)` would lose its exhaustiveness.
   */
  | UnknownCard;

export interface UnknownCard {
  type: "unknown";
  data: Record<string, unknown>;
}

// --- turns -------------------------------------------------------------------

export interface TurnMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  audioUrl?: string | null;
}

export interface TurnResponse {
  journeyId: string;
  version: number;
  /**
   * The engine's step.
   *
   * A plain `string`, not `Step`: an unknown step from a newer backend must
   * still decode rather than failing the whole response, exactly as the iOS
   * models do.
   */
  step: string;
  status: "active" | "completed" | "needs_human";
  progress: { index: number; total: number; label: string; etaSeconds: number };
  language: Lang;
  messages: TurnMessage[];
  card?: Card | null;
  quickReplies: { label: string; send: Record<string, unknown> }[];
  transcript?: string | null;
  detectedLanguage?: Lang | null;
  locks: { acceptEnabled: boolean; reason?: string | null };
  demoMode: boolean;
}

// --- dashboard ---------------------------------------------------------------

export interface Kpis {
  startedToday: number;
  completedToday: number;
  completionPct: number;
  medianSecondsToComplete: number | null;
  teachbackFirstAttemptPct: number;
  reexplanations: number;
  humanHandoffs: number;
  /** Low is good: it means nothing is being bundled (section 12). */
  insuranceOptInPct: number;
  /** A guard that never fires is worth a question (section 10.5). */
  guardBlocked: number;
  languageSplit: Record<string, number>;
  receiptsTotal: number;
  liveJourneys: number;
}

export interface FunnelStep {
  step: string;
  label: string;
  reached: number;
}

export interface QuestionStat {
  questionId: string;
  attempts: number;
  firstAttemptPassed: number;
  /** The number section 12 is really about: a low rate means the KFS is unclear. */
  firstAttemptPct: number;
  eventuallyPassed: number;
}

export interface Overview {
  kpis: Kpis;
  funnel: FunnelStep[];
  questions: QuestionStat[];
  generatedAt: string;
}

export interface JourneyRow {
  journeyId: string;
  personaId: string | null;
  personaName: string | null;
  language: string;
  step: string;
  status: string;
  amount: number | null;
  selectedOffer: string | null;
  durationSeconds: number;
  lastActivitySeconds: number;
  receiptNo: string | null;
  /** Drives the pulsing dot in the live table. */
  isLive: boolean;
}

export interface TimelineEvent {
  at: string;
  actor: string;
  eventType: string;
  step: string | null;
  data: Record<string, unknown>;
}

export interface TranscriptLine {
  turnNo: number;
  role: string;
  /** Decrypted server-side for an admin only (section 11.2). */
  text: string;
  source: string;
  at: string;
  sttMs: number | null;
  llmMs: number | null;
}

export interface AttemptRow {
  questionId: string;
  attemptNo: number;
  answerType: string;
  isCorrect: boolean;
  grader: string;
  at: string;
}

export interface ConsentRow {
  purpose: string;
  granted: boolean;
  /** Stored alongside `granted` to prove the toggle started off (section 6). */
  defaultValue: boolean;
  method: string;
  at: string;
}

export interface JourneyDetail {
  journey: JourneyRow;
  timeline: TimelineEvent[];
  transcript: TranscriptLine[];
  attempts: AttemptRow[];
  consents: ConsentRow[];
  suitability: {
    foir: number | null;
    decision: string;
    reasons: string[];
    incomeVerified: boolean;
    monthlyIncome: number | null;
  };
  receiptNo: string | null;
}

export interface ReceiptRow {
  receiptNo: string;
  seq: number;
  shortHash: string;
  lender: string;
  language: string;
  createdAt: string;
}

export interface RescueRow {
  taskId: string;
  journeyId: string;
  kind: string;
  reason: string;
  step: string;
  status: string;
  contactWindowOk: boolean;
  createdAt: string;
}

// --- receipts and verification -----------------------------------------------

export interface Check {
  name: string;
  ok: boolean;
  detail: string;
}

export interface VerifyResult {
  valid: boolean;
  checks: Check[];
  hash: string;
  prevHash: string;
  seq: number;
  keyId: string;
}

export interface CandidateResult extends VerifyResult {
  /** Field-level changes, for the tamper editor (section 11.3). */
  diff: { path: string; from: unknown; to: unknown }[];
  reasons: string[];
}

export interface ReceiptSummary {
  receiptNo: string;
  seq: number;
  lender: string;
  product: string;
  language: string;
  teachbackPassed: number;
  teachbackTotal: number;
  createdAt: string;
  shortHash: string;
  valid: boolean;
}

export interface ReceiptDetail extends ReceiptSummary {
  payload: Record<string, unknown>;
  checks: Check[];
}

export interface LedgerBlock {
  seq: number;
  receiptNo: string;
  prevHash: string;
  hash: string;
  keyId: string;
  createdAt: string;
}

export interface Anchor {
  day: string;
  merkleRoot: string;
  receiptCount: number;
}

export interface LedgerResponse {
  blocks: LedgerBlock[];
  lastSeq: number;
  /** Whether the whole chain walks cleanly, not just each block alone. */
  chainValid: boolean;
  problems: string[];
  todayAnchor: Anchor | null;
}

export interface PublicKey {
  keyId: string;
  publicKeyB64: string;
  active: boolean;
}

// --- SSE ---------------------------------------------------------------------

/** The event names of section 8.2. */
export type DashboardEventName =
  "journey.updated" | "receipt.created" | "rescue.created" | "guard.blocked" | "demo.reset";

export interface DashboardEvent {
  name: DashboardEventName;
  data: Record<string, unknown>;
}

// --- KFS ingestion (build plan 11, phase 11) ---------------------------------

export interface KfsField {
  key: string;
  raw: string;
  value: number | null;
  confidence: number | null;
  low: boolean;
  required: boolean;
}

export interface KfsDocumentRow {
  documentId: string;
  lender: string;
  offerId: string | null;
  version: string;
  status: "draft" | "verified" | "active" | "retired";
  source: string;
  engine: string | null;
  sha256: string;
  verifiedBy: string | null;
  verifiedAt: string | null;
  createdAt: string;
  originalFilename: string | null;
}

/** A trilingual block as the backend stores it. */
export type Trilingual = Record<string, string>;

export interface GeneratedOption {
  id: string;
  correct: boolean;
  text: Trilingual;
}

export interface GeneratedQuestion {
  factKey: string;
  sortOrder: number;
  prompt: Trilingual;
  options: GeneratedOption[];
  reexplain: Trilingual;
  rubric: Record<string, string[]>;
  /** "generated" by the model, or "seeded" when it was rejected or unavailable. */
  origin: "generated" | "seeded";
}

export interface KfsProposal {
  engine?: string;
  questions?: GeneratedQuestion[];
  explain?: Record<string, Trilingual>;
  blocked?: string[];
}

export interface KfsDocumentDetail extends KfsDocumentRow {
  fields: KfsField[];
  missingRequired: string[];
  sanityProblems: string[];
  lowConfidenceThreshold: number;
  clauseCount: number;
  fileUrl: string;
  generated: KfsProposal;
  canVerify: boolean;
  canPublish: boolean;
  canActivate: boolean;
}

export interface KfsOfferChoice {
  offerId: string;
  lender: string;
  activeVersion: string | null;
}

export interface KfsLibraryResponse {
  documents: KfsDocumentRow[];
  offers: KfsOfferChoice[];
}

export interface KfsPublishResponse {
  activated: boolean;
  engine: string;
  questions: GeneratedQuestion[];
  explain: Record<string, Trilingual>;
  blocked: string[];
  result: {
    documentId: string;
    offerId: string | null;
    version: string;
    retired: number;
    questions: number;
    emi: number;
    apr: number;
  } | null;
}
