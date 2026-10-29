/**
 * Auth context and its hook.
 *
 * Separate from `auth.tsx` so that file exports only the `AuthProvider`
 * component, which keeps React Fast Refresh working during the demo build.
 */
import { createContext, use } from "react";
import type { Me } from "@/lib/api";

export type AuthStatus = "loading" | "signedOut" | "signedIn";

export interface AuthContextValue {
  status: AuthStatus;
  /** The backend profile. Null until `GET /api/me` has returned. */
  me: Me | null;
  /** True for a dev demo session rather than a real Google sign-in. */
  isDemo: boolean;
  /** Last sign-in error, in words a person can act on. */
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signInAsDemoUser: () => Promise<void>;
  logout: () => Promise<void>;
  /** Re-fetch `/api/me`, e.g. after changing the language. */
  refreshMe: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Read the auth context. Throws if used outside `AuthProvider`. */
export function useAuth(): AuthContextValue {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
