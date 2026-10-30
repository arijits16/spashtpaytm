import { NavLink, Outlet } from "react-router";
import {
  Activity,
  FileCheck2,
  LayoutDashboard,
  Library,
  Link2,
  LogOut,
  PhoneCall,
  SlidersHorizontal,
} from "lucide-react";
import { useAuth } from "@/lib/authContext";

/**
 * Laptop shell for the lender / compliance dashboard (build plan 5.8, 12).
 *
 * Dark navy sidebar, white content area, minimum width 1100px. The pages
 * themselves land in phase 9; this is the frame they mount into, and it carries
 * the signed-in identity and Logout for the whole website.
 */
const NAV = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/dashboard/journeys", label: "Live journeys", icon: Activity, end: false },
  { to: "/dashboard/receipts", label: "Receipts", icon: FileCheck2, end: false },
  { to: "/dashboard/ledger", label: "Ledger", icon: Link2, end: false },
  { to: "/dashboard/kfs", label: "KFS library", icon: Library, end: false },
  { to: "/dashboard/rescue", label: "Rescue tasks", icon: PhoneCall, end: false },
  { to: "/dashboard/demo", label: "Demo controls", icon: SlidersHorizontal, end: false },
] as const;

export function DashboardLayout() {
  const { me, isDemo, logout } = useAuth();

  return (
    <div className="flex min-h-dvh min-w-[1100px] bg-white">
      <aside className="flex w-60 shrink-0 flex-col bg-[#0B1F44] text-white">
        <div className="px-5 py-5">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold tracking-tight">Spasht</span>
            <span className="rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-semibold">
              Concept
            </span>
          </div>
          <p className="mt-1 text-[11px] text-white/55">Lender &amp; compliance</p>
        </div>

        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                  isActive ? "bg-white/12 text-white" : "text-white/65 hover:bg-white/8",
                ].join(" ")
              }
            >
              <Icon size={16} strokeWidth={1.75} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Signed-in identity and the website's only Logout button. */}
        <div className="mt-auto border-t border-white/10 px-5 py-4">
          <p className="truncate text-[12px] font-semibold text-white/90">
            {me?.displayName ?? me?.email ?? "Signed in"}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-white/50">
            {isDemo ? "demo admin session" : (me?.email ?? "")}
          </p>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-3 flex items-center gap-1.5 rounded-full border border-white/25 px-3 py-1.5 text-[12px] font-semibold text-white/85 hover:bg-white/10"
          >
            <LogOut size={13} strokeWidth={2} aria-hidden />
            Logout
          </button>

          <p className="mt-4 text-[10px] leading-snug text-white/40">
            Concept demo · synthetic data only · not the live Paytm app
          </p>
        </div>
      </aside>

      <main className="bg-bg flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
