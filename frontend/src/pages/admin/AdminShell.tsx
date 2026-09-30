import { NavLink, Navigate, Outlet } from "react-router-dom";
import { Activity, FileText, Gauge, Radio, ScrollText, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/store/auth";
import { atLeast } from "@/lib/domain";
import { cn } from "@/lib/utils";

/**
 * System — the maintenance area.
 *
 * This sidebar used to carry nine entries and contained the platform's two most
 * important screens, the alert queue and the verification queue, filed between
 * "Reports" and "Audit Log" as though issuing a red warning were an
 * administrative chore. Those moved to Advise and Verify. What is left here is
 * genuinely administration: what the collectors are doing, what arrived, and
 * what the pipeline did with it.
 */
const NAV = [
  { to: "/admin/sources", label: "Sources", icon: Radio },
  { to: "/admin/credibility", label: "Credibility", icon: ShieldAlert },
  { to: "/admin/reports", label: "Reports", icon: FileText },
  { to: "/admin/events", label: "Events", icon: Activity },
  { to: "/admin/health", label: "Pipeline health", icon: Gauge },
  { to: "/admin/audit", label: "Audit log", icon: ScrollText },
];

export function AdminShell() {
  const { user, loading } = useAuth();

  if (loading) return <div className="h-full bg-[var(--surface-base)]" />;
  if (!atLeast(user?.role, "ANALYST")) return <Navigate to="/login" replace />;

  return (
    <AppShell>
      <div className="flex min-h-0 flex-1">
        <nav className="flex w-[232px] shrink-0 flex-col gap-1 divider-y p-4">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "relative flex items-center gap-3 rounded-[var(--r-md)] px-3.5 py-3 text-[15px] transition-colors duration-150",
                  isActive
                    ? "bg-[var(--veil-1)] font-medium text-[var(--text-ink)]"
                    : "text-[var(--text-faint)] hover:bg-[var(--veil-2)] hover:text-[var(--text-dim)]",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      "absolute inset-y-1.5 left-0 w-[2px] rounded-full",
                      isActive ? "bg-[var(--accent)]" : "bg-transparent",
                    )}
                  />
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <main className="min-w-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </AppShell>
  );
}
