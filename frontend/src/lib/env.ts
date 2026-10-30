/**
 * Env-derived feature flags.
 *
 * Kept in a plain module (no components) so importing a flag never breaks React
 * Fast Refresh in the files that use it.
 */

/** The shared secret the backend compares against `DEMO_AUTH_KEY` (plan 13.2). */
export const DEMO_AUTH_KEY: string = import.meta.env.VITE_DEMO_AUTH_KEY ?? "";

/**
 * Shows "Continue as demo admin" and sends the demo headers.
 *
 * Both halves are required: the flag alone is useless because the backend now
 * demands a matching `X-Demo-Key`, so offering the button without a key would
 * only ever produce a confusing 401.
 */
export const DEMO_AUTH_ENABLED: boolean =
  import.meta.env.VITE_DEMO_AUTH === "true" && DEMO_AUTH_KEY.length > 0;

/**
 * The website signs in as the dashboard operator, not as a customer.
 *
 * `sunita` is the iPhone app's identity; this is a laptop dashboard, so using
 * her here would show a customer with no admin rights (plan 13.2).
 */
export const DEMO_PERSONA = "demo-admin";

/** sessionStorage key holding an active demo session, so refresh survives. */
export const DEMO_SESSION_KEY = "spasht.demoUser";
