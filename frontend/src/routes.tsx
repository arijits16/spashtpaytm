import { createBrowserRouter } from "react-router";
import { SiteLayout } from "@/components/SiteLayout";
import { DashboardLayout } from "@/features/dashboard/DashboardLayout";
import { DemoControls } from "@/features/dashboard/DemoControls";
import { KfsLibrary } from "@/features/dashboard/KfsLibrary";
import { Ledger } from "@/features/dashboard/Ledger";
import { LiveJourneys } from "@/features/dashboard/LiveJourneys";
import { Overview } from "@/features/dashboard/Overview";
import { ReceiptCheck } from "@/features/dashboard/ReceiptCheck";
import { Receipts } from "@/features/dashboard/Receipts";
import { RescueTasks } from "@/features/dashboard/RescueTasks";
import { IndexRedirect, RedirectIfSignedIn, RequireAdmin } from "@/lib/guards";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";

/**
 * Route table for the laptop website (build plan 5.8).
 *
 * Three routes and a catch-all: `/` redirects, `/login` is the only public
 * page, and `/dashboard/*` needs an admin. There are deliberately **no phone
 * routes** - the customer journey lives in the native iOS app (v2).
 */
export const router = createBrowserRouter([
  {
    element: <SiteLayout />,
    children: [
      { path: "/", element: <IndexRedirect /> },
      {
        element: <RedirectIfSignedIn />,
        children: [{ path: "/login", element: <LoginPage /> }],
      },
      {
        element: <RequireAdmin />,
        children: [
          {
            path: "/dashboard",
            element: <DashboardLayout />,
            children: [
              { index: true, element: <Overview /> },
              { path: "journeys", element: <LiveJourneys /> },
              { path: "receipts", element: <Receipts /> },
              // The receipt check and its tamper editor (5.8, 11.3).
              { path: "receipts/:receiptNo", element: <ReceiptCheck /> },
              { path: "ledger", element: <Ledger /> },
              { path: "kfs", element: <KfsLibrary /> },
              { path: "rescue", element: <RescueTasks /> },
              { path: "demo", element: <DemoControls /> },
            ],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
