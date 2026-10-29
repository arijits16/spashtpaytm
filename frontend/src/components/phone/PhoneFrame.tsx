import type { ReactNode } from "react";
import { ConceptRibbon } from "./ConceptRibbon";
import { SafeArea } from "./SafeArea";

/**
 * Phone shell for the customer routes (build plan 5.8).
 *
 * On a screen >= 500px wide (the judges' laptop) the app renders inside a
 * 390x844 bezel so it reads as a phone. On a real phone the frame collapses to
 * full screen with safe-area insets. One component, both renderings - no
 * duplicated layout to keep in sync.
 */
export function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="bg-bg flex min-h-dvh justify-center frame:items-center frame:bg-slate-200 frame:py-6">
      {/* The bezel exists only at >= frame (500px); below that these classes are inert. */}
      <div
        className={[
          "bg-bg relative flex min-h-dvh w-full flex-col overflow-hidden",
          "frame:h-[844px] frame:max-h-[844px] frame:min-h-0 frame:w-[390px]",
          "frame:rounded-[44px] frame:border-[10px] frame:border-slate-900 frame:shadow-2xl",
        ].join(" ")}
      >
        <FakeStatusBar />
        <ConceptRibbon />
        <SafeArea>
          <main className="no-scrollbar flex-1 overflow-y-auto">{children}</main>
        </SafeArea>
      </div>
    </div>
  );
}

/**
 * Cosmetic status bar, shown only inside the desktop bezel. On a real phone the
 * OS draws the real one, so this would be a duplicate.
 */
function FakeStatusBar() {
  return (
    <div
      aria-hidden
      className="text-text-1 hidden items-center justify-between px-6 pt-2 pb-1 text-[11px] font-semibold frame:flex"
    >
      <span>9:41</span>
      <span className="flex items-center gap-1">
        <span className="tracking-tighter">●●●</span>
        <span>▮</span>
      </span>
    </div>
  );
}
