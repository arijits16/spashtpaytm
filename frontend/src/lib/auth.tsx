/**
 * AuthProvider (build plan phase 1, step 2).
 *
 * Holds the Firebase user, wires `getIdToken()` into the API client so every
 * request carries a fresh token, and exposes the backend profile from
 * `GET /api/me`. Also supports the dev "demo user" path, which needs no network.
 *
 * The context and `useAuth` live in `authContext.ts`; this file exports only the
 * component, so Fast Refresh keeps working.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { getMe, setAuthTokenProvider, setDemoUser, type Me } from "@/lib/api";
import { AuthContext, type AuthContextValue, type AuthStatus } from "@/lib/authContext";
import { DEMO_AUTH_ENABLED, DEMO_PERSONA, DEMO_SESSION_KEY } from "@/lib/env";
import { getFirebaseAuth, googleProvider, isFirebaseConfigured } from "@/lib/firebase";

/** Outcome of a `/api/me` call. Pure data - no React state is touched here. */
type MeResult = { ok: true; me: Me } | { ok: false; error: unknown };

/** Fetch the backend profile, turning a throw into a value. */
async function fetchMe(): Promise<MeResult> {
  try {
    return { ok: true, me: await getMe() };
  } catch (error) {
    return { ok: false, error };
  }
}

/** True when a demo session was left open in this tab. */
function hasStoredDemoSession(): boolean {
  return DEMO_AUTH_ENABLED && sessionStorage.getItem(DEMO_SESSION_KEY) === DEMO_PERSONA;
}

/**
 * Resolve the starting status synchronously, before the first paint.
 *
 * Doing this here rather than in an effect avoids a cascading re-render and a
 * flash of the login screen for an already-signed-in user.
 */
function initialStatus(): AuthStatus {
  if (hasStoredDemoSession()) return "loading";
  // Nothing to restore and no Firebase to ask: settle immediately.
  if (!isFirebaseConfigured) return "signedOut";
  return "loading";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(initialStatus);
  const [isDemo, setIsDemo] = useState<boolean>(hasStoredDemoSession);
  const [me, setMe] = useState<AuthContextValue["me"]>(null);
  const [error, setError] = useState<string | null>(null);

  // Held in a ref so the token-provider closure never goes stale.
  const firebaseUser = useRef<User | null>(null);

  /** Clear every trace of a demo session (module state, storage, React state). */
  const clearDemoSession = useCallback(() => {
    sessionStorage.removeItem(DEMO_SESSION_KEY);
    setDemoUser(null);
    setIsDemo(false);
  }, []);

  /**
   * Apply the outcome of a `/api/me` fetch to the session.
   *
   * A failure signs the session out rather than leaving the UI
   * half-authenticated. Called only from async callbacks, never during render.
   */
  const applyMe = useCallback(
    (result: MeResult) => {
      if (result.ok) {
        setMe(result.me);
        setStatus("signedIn");
        return;
      }
      console.error("[spasht] /api/me failed", result.error);
      setError("Signed in, but the backend rejected the session.");
      clearDemoSession();
      setStatus("signedOut");
    },
    [clearDemoSession],
  );

  // --- token provider: consulted by the API client before every request ------
  useEffect(() => {
    setAuthTokenProvider(async () => {
      const user = firebaseUser.current;
      if (!user) return null;
      // Firebase refreshes the token automatically when it nears expiry.
      return user.getIdToken();
    });
  }, []);

  // --- restore a demo session left open in this tab (dev only) ---------------
  useEffect(() => {
    if (!hasStoredDemoSession()) return;

    setDemoUser(DEMO_PERSONA);
    void fetchMe().then(applyMe);
  }, [applyMe]);

  // --- real Firebase session -------------------------------------------------
  useEffect(() => {
    // Not configured: `initialStatus` already settled on "signedOut", and the
    // login page explains what is missing.
    if (!isFirebaseConfigured) return;

    const unsubscribe = onAuthStateChanged(getFirebaseAuth(), (user) => {
      firebaseUser.current = user;

      if (!user) {
        // Do not clobber an active demo session.
        if (hasStoredDemoSession()) return;
        setMe(null);
        setIsDemo(false);
        setStatus("signedOut");
        return;
      }

      // A real token outranks any demo session.
      clearDemoSession();
      void fetchMe().then(applyMe);
    });

    return unsubscribe;
  }, [applyMe, clearDemoSession]);

  // --- actions ---------------------------------------------------------------

  const signInWithGoogle = useCallback(async () => {
    setError(null);
    if (!isFirebaseConfigured) {
      setError("Firebase is not configured. Fill VITE_FIREBASE_* in frontend/.env.");
      return;
    }
    try {
      // Must run inside a user gesture, or the browser blocks the popup.
      await signInWithPopup(getFirebaseAuth(), googleProvider());
      // onAuthStateChanged takes it from here.
    } catch (err) {
      setError(describeSignInError(err));
    }
  }, []);

  const signInAsDemoUser = useCallback(async () => {
    setError(null);
    if (!DEMO_AUTH_ENABLED) {
      setError("Demo sign-in is disabled. Set VITE_DEMO_AUTH=true in frontend/.env.");
      return;
    }

    // End any real Firebase session first. The API client prefers a bearer
    // token over `X-Demo-User`, so leaving one in place would keep the real
    // identity active while the UI claimed to be in a demo session.
    if (isFirebaseConfigured) {
      try {
        await signOut(getFirebaseAuth());
      } catch (err) {
        console.warn("[spasht] firebase signOut before demo sign-in failed", err);
      }
    }
    firebaseUser.current = null;

    setDemoUser(DEMO_PERSONA);
    sessionStorage.setItem(DEMO_SESSION_KEY, DEMO_PERSONA);
    setIsDemo(true);

    const result = await fetchMe();
    applyMe(result);
    if (!result.ok) {
      setError("Demo sign-in failed. Is the backend running with DEMO_AUTH=true?");
    }
  }, [applyMe]);

  const logout = useCallback(async () => {
    clearDemoSession();
    setMe(null);
    firebaseUser.current = null;

    if (isFirebaseConfigured) {
      try {
        await signOut(getFirebaseAuth());
      } catch (err) {
        console.warn("[spasht] firebase signOut failed", err);
      }
    }
    setStatus("signedOut");
  }, [clearDemoSession]);

  const refreshMe = useCallback(async () => {
    applyMe(await fetchMe());
  }, [applyMe]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      isDemo,
      error,
      signInWithGoogle,
      signInAsDemoUser,
      logout,
      refreshMe,
    }),
    [status, me, isDemo, error, signInWithGoogle, signInAsDemoUser, logout, refreshMe],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

/** Turn a Firebase error code into something a person can act on. */
function describeSignInError(err: unknown): string {
  const code = typeof err === "object" && err !== null && "code" in err ? String(err.code) : "";

  switch (code) {
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "Sign-in was cancelled.";
    case "auth/popup-blocked":
      return "Your browser blocked the sign-in popup. Allow popups and try again.";
    case "auth/unauthorized-domain":
      return "This domain is not in the Firebase authorized-domains list.";
    case "auth/network-request-failed":
      return "No network. Use “Continue as demo user” if it is enabled.";
    case "auth/operation-not-allowed":
      return "Google sign-in is not enabled in the Firebase console.";
    default:
      return code ? `Sign-in failed (${code}).` : "Sign-in failed. Please try again.";
  }
}
