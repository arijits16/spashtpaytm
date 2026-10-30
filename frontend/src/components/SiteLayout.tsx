import { Outlet } from "react-router";
import { ConceptRibbon } from "@/components/ConceptRibbon";

/**
 * Root layout for the laptop website (build plan 5.8).
 *
 * The website is laptop-only in v2: there are no phone pages and no phone
 * bezel - the customer side is the native iPhone app. All this layout does is
 * keep the concept ribbon above every page.
 */
export function SiteLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <ConceptRibbon />
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  );
}
