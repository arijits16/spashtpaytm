/** Dashboard overview. KPIs, funnel and charts arrive in phase 9 (build plan 12). */
export function Overview() {
  return (
    <div className="p-8">
      <h1 className="text-text-1 text-2xl font-bold">Overview</h1>
      <p className="text-text-3 mt-1 text-sm">
        KPIs, the step funnel and per-question teach-back pass rates arrive in phase 9.
      </p>

      <div className="mt-6 grid grid-cols-4 gap-3">
        {["Journeys today", "Completed", "Teach-back 1st-try pass", "AI numbers blocked"].map(
          (label) => (
            <div key={label} className="rounded-card border border-slate-200 bg-white p-5">
              <p className="text-text-3 text-[11px] font-medium uppercase tracking-wide">{label}</p>
              <p className="text-text-3/40 mt-2 text-3xl font-bold">—</p>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
