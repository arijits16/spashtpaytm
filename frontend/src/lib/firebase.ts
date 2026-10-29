/**
 * Firebase client initialisation (build plan phase 1).
 *
 * Only Authentication is used. The config below is public by design - it ships
 * in the client bundle and identifies the project; it is not a secret. Access
 * is controlled by Firebase's authorized-domains list and by backend token
 * verification, never by hiding these values.
 */
import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  getAuth,
  setPersistence,
  type Auth,
} from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY ?? "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID ?? "",
} as const;

/**
 * True when the four values the Auth SDK needs are present.
 *
 * When false the app does not crash: the login page hides the Google button and
 * explains what is missing, so a teammate with no .env still gets a usable app
 * (and `Continue as demo user`, if enabled).
 */
export const isFirebaseConfigured: boolean = Object.values(config).every((v) => v.length > 0);

let app: FirebaseApp | undefined;
let auth: Auth | undefined;

/**
 * Lazily initialise Firebase and return the Auth instance.
 *
 * @throws Error when the environment is not configured - callers should check
 *         `isFirebaseConfigured` first.
 */
export function getFirebaseAuth(): Auth {
  if (!isFirebaseConfigured) {
    throw new Error("Firebase is not configured: fill VITE_FIREBASE_* in frontend/.env");
  }
  if (!auth) {
    app ??= initializeApp(config);
    auth = getAuth(app);
    // Survive a page refresh, which the demo relies on. Failure is non-fatal:
    // the session simply becomes tab-scoped.
    void setPersistence(auth, browserLocalPersistence).catch(() => {
      console.warn("[spasht] local auth persistence unavailable; session is tab-scoped");
    });
  }
  return auth;
}

/** Google provider. `prompt: select_account` avoids silently reusing an account. */
export function googleProvider(): GoogleAuthProvider {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  return provider;
}
