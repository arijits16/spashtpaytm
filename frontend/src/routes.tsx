import { createBrowserRouter } from "react-router";
import { SiteLayout } from "@/components/SiteLayout";
import { DashboardLayout } from "@/features/dashboard/DashboardLayout";
import { Overview } from "@/features/dashboard/Overview";
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
            children: [{ index: true, element: <Overview /> }],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
