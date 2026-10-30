import { Navigate, Outlet, useLocation } from "react-router";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/authContext";
import { NotAllowed } from "@/pages/NotAllowed";

/**
 * Route guards for the laptop website (build plan 5.8).
 *
 * The website has exactly one protected area, `/dashboard/*`, and it needs an
 * admin on the `DASHBOARD_ADMIN_EMAILS` allowlist. These guards are a UX
 * convenience only - the backend enforces the same rules independently
 * (401 / 403), so bypassing the frontend gains nothing.
 */

function FullScreenSpinner({ label }: { label: string }) {
  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center gap-3"
      role="status"
      aria-live="polite"
    >
      <Loader2 size={22} className="text-navy animate-spin" aria-hidden />
      <p className="text-text-3 text-body">{label}</p>
    </div>
  );
}

/** Requires an admin. Non-admins get a plain explanation, not a redirect loop. */
export function RequireAdmin() {
  const { status, me } = useAuth();
  const location = useLocation();

  // `signedIn` with a null profile means `/api/me` is still in flight; showing
  // "access required" then would be a lie that resolves a moment later.
  if (status === "loading" || (status === "signedIn" && me === null)) {
    return <FullScreenSpinner label="Checking your access…" />;
  }
  if (status === "signedOut") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  // `me` is non-null by here (the spinner branch covers the in-flight case);
  // the optional chain keeps that fact from depending on control-flow narrowing.
  if (!me?.isAdmin) return <NotAllowed />;

  return <Outlet />;
}

/** Keeps a signed-in user off `/login` by bouncing them to the dashboard. */
export function RedirectIfSignedIn() {
  const { status } = useAuth();

  if (status === "loading") return <FullScreenSpinner label="Checking your session…" />;
  if (status === "signedIn") return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

/**
 * `/` is not a page: it sends you to the dashboard or to login (build plan 5.8).
 *
 * The admin check is left to `RequireAdmin` so a non-admin lands on one clear
 * explanation rather than bouncing between routes.
 */
export function IndexRedirect() {
  const { status } = useAuth();

  if (status === "loading") return <FullScreenSpinner label="Checking your session…" />;
  return <Navigate to={status === "signedIn" ? "/dashboard" : "/login"} replace />;
}
