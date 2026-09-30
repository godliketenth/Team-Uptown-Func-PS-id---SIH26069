import { Link, NavLink, useLocation } from "react-router-dom";
import { LogOut, Moon, Settings2, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterBar } from "@/components/dashboard/FilterBar";
import { useAuth } from "@/store/auth";
import { atLeast } from "@/lib/domain";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

/**
 * The three-mode workspace.
 *
 * The console used to be one screen trying to serve three different jobs at
 * once: watching the country, deciding whether a report is real, and getting a
 * warning out. They want opposite things from a layout — the first wants a map,
 * the second wants evidence side by side with a queue and no map at all, the
 * third wants a worklist — so the single screen compromised on all three and
 * the actual decisions ended up behind a slide-over.
 *
 * Monitor, Verify and Advise are now separate destinations, each built for one
 * job. `/admin` keeps the system-level pages (sources, reports, health, audit),
 * which are maintenance rather than operations.
 *
 * Filters also get their own full-width row here. In the old single-row bar
 * they were squeezed between the wordmark and the user menu and dropped out by
 * breakpoint — state below 1280px, district below 1536px — so on an ordinary
 * laptop it was impossible to filter by district at all, which the platform is
 * explicitly required to support.
 */

const MODES = [
  { to: "/monitor", label: "Monitor", hint: "What is happening across India right now" },
  { to: "/verify", label: "Verify", hint: "Decide whether a reported event is real" },
  { to: "/advise", label: "Advise", hint: "Warnings issued, and what still needs issuing" },
];

export function AppShell({
  showFilters = false,
  children,
}: {
  showFilters?: boolean;
  children: React.ReactNode;
}) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const location = useLocation();
  const inAdmin = location.pathname.startsWith("/admin");

  return (
    <div className="flex h-full flex-col">
      <header className="chrome relative z-30 shrink-0">
        <div className="flex h-[68px] items-center gap-8 px-7">
          {/* The emblem only — the supplied lockup sets "NATIONAL / WEATHER
              ANALYTICS DASHBOARD" in dark navy beneath the mark, which would be
              invisible on this ground and would also put a second typeface next
              to the interface's own. The wordmark is set in Plex instead. */}
          <Link to="/monitor" className="flex shrink-0 items-center gap-3.5">
            <img
              src="/logo-mark.png"
              alt=""
              width={32}
              height={32}
              className="h-9 w-9 shrink-0 select-none"
              draggable={false}
            />
            <span className="hidden text-[18px] font-bold leading-none text-[var(--text-ink)] sm:inline">
              National Weather Analytics
            </span>
          </Link>

          <nav className="flex h-full items-stretch gap-2" aria-label="Workspace">
            {MODES.map((m) => (
              <NavLink
                key={m.to}
                to={m.to}
                title={m.hint}
                className={({ isActive }) =>
                  cn(
                    "relative flex items-center px-4 text-[16px] font-bold transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/55",
                    isActive
                      ? "text-[var(--text-ink)]"
                      : "text-[var(--text-faint)] hover:text-[var(--text-dim)]",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {m.label}
                    {/* The active mode is marked by a rule under it, not a
                        filled pill: the modes are places, not buttons. */}
                    <span
                      className={cn(
                        "absolute inset-x-2.5 bottom-0 h-[2px] transition-opacity",
                        isActive ? "bg-[var(--accent)] opacity-100" : "opacity-0",
                      )}
                    />
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              title="Toggle theme"
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            </Button>

            {atLeast(user?.role, "ANALYST") && (
              <Link to={inAdmin ? "/monitor" : "/admin"}>
                <Button variant={inAdmin ? "default" : "ghost"} size="md">
                  <Settings2 className="h-3.5 w-3.5" />
                  System
                </Button>
              </Link>
            )}

            {user ? (
              <div className="flex items-center gap-2.5">
                <div className="hidden text-right leading-tight lg:block">
                  <div className="text-[13px] text-[var(--text-dim)]">{user.email}</div>
                  <div className="text-[12px] text-[var(--text-faint)]">
                    {user.role.replace("_", " ").toLowerCase()}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={logout}
                  title="Sign out"
                  aria-label="Sign out"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <Link to="/login">
                <Button variant="outline" size="md">
                  Sign in
                </Button>
              </Link>
            )}
          </div>
        </div>

        {showFilters && (
          <div className="flex h-[52px] items-center gap-2 border-t border-[var(--hairline-soft)] px-7">
            <FilterBar />
          </div>
        )}
      </header>

      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
