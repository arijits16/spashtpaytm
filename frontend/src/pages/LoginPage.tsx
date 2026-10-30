import { useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/authContext";
import { DEMO_AUTH_ENABLED } from "@/lib/env";
import { isFirebaseConfigured } from "@/lib/firebase";

/**
 * Website login (build plan 5.8).
 *
 * Laptop-only: this is the door to the lender and compliance dashboard, so it
 * is centred in the viewport rather than laid out for a phone. Light-blue
 * gradient, a text wordmark plus a `Concept` pill, `Continue with Google`, and
 * - only when `VITE_DEMO_AUTH=true` - a demo path that needs no network.
 *
 * Customers do not log in here; they use the Spasht iPhone app.
 */
export function LoginPage() {
  const { signInWithGoogle, signInAsDemoUser, error } = useAuth();
  const [busy, setBusy] = useState<"google" | "demo" | null>(null);

  /** Wrap an action so the button cannot be double-fired. */
  const run = (kind: "google" | "demo", action: () => Promise<void>) => () => {
    if (busy) return;
    setBusy(kind);
    void action().finally(() => setBusy(null));
  };

  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center gap-8 px-6 py-12 text-center"
      style={{ background: "var(--login-grad)" }}
    >
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-baseline gap-2">
          {/* Plain text wordmark - never the official two-tone logo artwork (5.1). */}
          <span className="text-navy text-[34px] leading-none font-bold tracking-tight">Paytm</span>
          <span className="bg-badge-new text-text-1 rounded-full px-2 py-0.5 text-[10px] font-bold">
            Concept
          </span>
        </div>
        <p className="text-text-2 mt-1 text-body font-medium">Spasht · loans you understand</p>
        <p className="text-text-3 text-caption">Lender &amp; compliance dashboard</p>
      </div>

      <div className="flex w-full max-w-[340px] flex-col gap-3">
        {error && (
          <p
            role="alert"
            className="bg-alert-pink text-danger flex items-start gap-2 rounded-banner px-3 py-2 text-left text-caption"
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden />
            <span>{error}</span>
          </p>
        )}

        {isFirebaseConfigured ? (
          <GoogleButton busy={busy === "google"} onClick={run("google", signInWithGoogle)} />
        ) : (
          <p className="text-text-3 rounded-banner border border-dashed border-slate-300 px-3 py-2 text-caption">
            Google sign-in is unavailable: fill <code>VITE_FIREBASE_*</code> in{" "}
            <code>frontend/.env</code>.
          </p>
        )}

        {DEMO_AUTH_ENABLED && (
          <button
            type="button"
            onClick={run("demo", signInAsDemoUser)}
            disabled={busy !== null}
            className="text-text-2 rounded-full border border-slate-300 bg-white/70 py-3 text-body font-semibold disabled:opacity-60"
          >
            {busy === "demo" ? "Signing in…" : "Continue as demo admin"}
          </button>
        )}
      </div>

      <p className="text-text-3 max-w-[360px] text-[11px] leading-snug">
        Concept prototype for Paytm Build for India AI Hackathon · not the live Paytm app ·
        synthetic data only
      </p>
    </div>
  );
}

/**
 * Google sign-in button following Google's branding guidance: white surface,
 * the four-colour "G", Roboto-ish label, minimum height, unmodified mark.
 */
function GoogleButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="flex h-12 w-full items-center justify-center gap-3 rounded-full border border-[#747775] bg-white text-body font-medium text-[#1f1f1f] disabled:opacity-60"
    >
      {busy ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <GoogleMark />}
      <span>{busy ? "Opening Google…" : "Continue with Google"}</span>
    </button>
  );
}

/** Google's "G" mark, drawn to spec and never recoloured or distorted. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden focusable="false">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
