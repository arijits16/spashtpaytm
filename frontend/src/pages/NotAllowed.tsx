import { useAuth } from "@/lib/authContext";

/**
 * Shown to a signed-in non-admin who opens `/dashboard` (build plan 5.8).
 *
 * Cosmetic only: the backend independently returns 403 on every admin route, so
 * a user who skips past this screen still sees no data.
 */
export function NotAllowed() {
  const { me, logout } = useAuth();
  const email = me?.email ?? null;

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-white px-6 text-center">
      <p className="text-navy text-2xl font-bold">Dashboard access required</p>
      <p className="text-text-3 max-w-md text-body">
        {email ? <>Signed in as {email}. That account</> : <>This account</>} is not on the
        compliance allowlist. Add it to <code>DASHBOARD_ADMIN_EMAILS</code> in{" "}
        <code>backend/.env</code>, restart the backend, and sign in again.
      </p>
      <p className="text-text-3 max-w-md text-caption">
        The email must also be verified by Google — an unverified address is never treated as an
        admin.
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
