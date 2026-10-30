/**
 * Mandatory concept-demo label (build plan 5.1).
 *
 * The website imitates nothing of Paytm's app, but it does carry the Paytm
 * wordmark on the login screen, so the ribbon is what keeps that honest. It
 * must stay visible on every page and must not be dismissible.
 */
export function ConceptRibbon() {
  return (
    <div
      role="note"
      className="bg-navy px-4 py-1 text-center text-[11px] leading-[16px] font-medium tracking-wide text-white/90"
    >
      Concept demo · Paytm Build for India AI Hackathon · not the live Paytm app
    </div>
  );
}
