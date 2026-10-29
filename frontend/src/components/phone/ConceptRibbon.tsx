/**
 * Mandatory concept-demo label (build plan 5.1).
 *
 * This must stay visible on every phone screen: the shell imitates Paytm's
 * layout, so the ribbon is what keeps that honest. Do not make it dismissible.
 */
export function ConceptRibbon() {
  return (
    <div
      role="note"
      className="bg-navy px-screen py-1 text-center text-[10px] leading-[14px] font-medium tracking-wide text-white/90"
    >
      Concept demo · Paytm Build for India AI Hackathon · not the live Paytm app
    </div>
  );
}
