import { createBrowserRouter } from "react-router";
import { PhoneLayout } from "@/components/phone/PhoneLayout";
import { DashboardLayout } from "@/features/dashboard/DashboardLayout";
import { Overview } from "@/features/dashboard/Overview";
import { RedirectIfSignedIn, RequireAdmin, RequireAuth } from "@/lib/guards";
import { HomePlaceholder } from "@/pages/HomePlaceholder";
import { LoginPage } from "@/pages/LoginPage";
import { NotFound } from "@/pages/NotFound";

/**
 * Route table (build plan 5.8 and phase 1).
 *
 * Phone routes render inside `PhoneFrame` and need a signed-in user;
 * `/dashboard/*` renders the desktop layout and needs an admin. `/login` is the
 * only phone route open to visitors, and it bounces a signed-in user home.
 */
export const router = createBrowserRouter([
  {
    element: <PhoneLayout />,
    children: [
      {
        element: <RedirectIfSignedIn />,
        children: [{ path: "/login", element: <LoginPage /> }],
      },
      {
        element: <RequireAuth />,
        children: [{ path: "/", element: <HomePlaceholder /> }],
      },
      { path: "*", element: <NotFound /> },
    ],
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
]);
