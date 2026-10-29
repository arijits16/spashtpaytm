import type { ReactNode } from "react";

/**
 * Applies iOS safe-area insets. Inside the desktop PhoneFrame the insets are
 * zero, so the same component works in both renderings.
 */
export function SafeArea({ children }: { children: ReactNode }) {
  return <div className="pt-safe pb-safe flex min-h-0 flex-1 flex-col">{children}</div>;
}
