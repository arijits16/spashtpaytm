import { Navigate, Outlet, useLocation } from "react-router";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/authContext";

/**
 * Route guards (build plan phase 1, step 2).
 *
 * Phone routes need a signed-in user; `/dashboard` additionally needs an admin
 * on the `DASHBOARD_ADMIN_EMAILS` allowlist. These are a UX convenience only -
 * the backend enforces the same rules independently (401 / 403), so bypassing
 * the frontend gains nothing.
 */

function FullScreenSpinner({ label }: { label: string }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3" role="status">
      <Loader2 size={22} className="text-navy animate-spin" aria-hidden />
      <p className="text-text-3 text-body">{label}</p>
    </div>
  );
}

/** Requires any signed-in user. Sends visitors to /login, remembering where they were. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullScreenSpinner label="Checking your session…" />;
  if (status === "signedOut") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** Requires an admin. Non-admins get a plain explanation, not a redirect loop. */
export function RequireAdmin() {
  const { status, me } = useAuth();
  const location = useLocation();

  if (status === "loading" || (status === "signedIn" && me === null)) {
    return <FullScreenSpinner label="Checking your access…" />;
  }
  if (status === "signedOut") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!me?.isAdmin) return <NotAnAdmin email={me?.email ?? null} />;

  return <Outlet />;
}

/** Shown to a signed-in non-admin who opens /dashboard. */
function NotAnAdmin({ email }: { email: string | null }) {
  const { logout } = useAuth();

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-white px-6 text-center">
      <p className="text-navy text-2xl font-bold">Dashboard access required</p>
      <p className="text-text-3 max-w-md text-body">
        {email ? <>Signed in as {email}. That account</> : <>This account</>} is not on the
        compliance allowlist. Add it to <code>DASHBOARD_ADMIN_EMAILS</code> in{" "}
        <code>backend/.env</code> and sign in again.
      </p>
      <button
        type="button"
        onClick={() => void logout()}
        className="bg-navy mt-2 rounded-full px-5 py-2.5 text-body font-semibold text-white"
      >
        Sign out
      </button>
    </div>
  );
}

/** Keeps a signed-in user off /login by bouncing them home. */
export function RedirectIfSignedIn() {
  const { status } = useAuth();

  if (status === "loading") return <FullScreenSpinner label="Checking your session…" />;
  if (status === "signedIn") return <Navigate to="/" replace />;
  return <Outlet />;
}
