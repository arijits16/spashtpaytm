/**
 * Env-derived feature flags.
 *
 * Kept in a plain module (no components) so importing a flag never breaks React
 * Fast Refresh in the files that use it.
 */

/** Shows "Continue as demo user" and sends `X-Demo-User`. Dev convenience only. */
export const DEMO_AUTH_ENABLED: boolean = import.meta.env.VITE_DEMO_AUTH === "true";

/** The persona a demo session signs in as (plan 7.1: the golden persona). */
export const DEMO_PERSONA = "sunita";

/** sessionStorage key holding an active demo session, so refresh survives. */
export const DEMO_SESSION_KEY = "spasht.demoUser";
