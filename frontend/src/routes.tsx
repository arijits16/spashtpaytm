import { createBrowserRouter } from "react-router";
import { PhoneLayout } from "@/components/phone/PhoneLayout";
import { DashboardLayout } from "@/features/dashboard/DashboardLayout";
import { Overview } from "@/features/dashboard/Overview";
import { HomePlaceholder } from "@/pages/HomePlaceholder";
import { NotFound } from "@/pages/NotFound";

/**
 * Route table (build plan 5.8).
 *
 * Two layouts: phone routes render inside `PhoneFrame`, `/dashboard/*` renders
 * the desktop `DashboardLayout`. Route guards are added in phase 1.
 */
export const router = createBrowserRouter([
  {
    element: <PhoneLayout />,
    children: [
      { path: "/", element: <HomePlaceholder /> },
      { path: "*", element: <NotFound /> },
    ],
  },
  {
    path: "/dashboard",
    element: <DashboardLayout />,
    children: [{ index: true, element: <Overview /> }],
  },
]);
