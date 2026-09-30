import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { AdminAlerts } from "@/pages/admin/AdminAlerts";
import { AdminPreparedness } from "@/pages/admin/AdminPreparedness";
import { api } from "@/lib/api";
import { livePoll } from "@/lib/live";
import { useAuth } from "@/store/auth";
import { cn } from "@/lib/utils";

/**
 * Advise — the output.
 *
 * One question: what have we told people, and what still needs telling. The
 * alert queue and the preparedness view were previously two unrelated entries
 * in a nine-item admin sidebar, which framed them as administration. They are
 * not: issuing a warning is the reason the platform exists, and the two views
 * are the same job seen forward and backward — what to send now, and whether
 * what was sent is reaching the districts that need it.
 */

type Tab = "alerts" | "preparedness";

export function Advise() {
  const [tab, setTab] = React.useState<Tab>("alerts");
  const user = useAuth((s) => s.user);

  const { data: summary } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: api.alertSummary,
    refetchInterval: livePoll(5000),
    enabled: Boolean(user),
  });

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "alerts", label: "Alerts", count: summary?.active },
    { id: "preparedness", label: "Preparedness", count: undefined },
  ];

  return (
    <AppShell>
      <div className="flex h-[46px] shrink-0 items-stretch gap-2 divider-x px-7">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
            className={cn(
              "relative cursor-pointer px-4 text-[15px] transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/55",
              tab === t.id
                ? "font-medium text-[var(--text-ink)]"
                : "text-[var(--text-faint)] hover:text-[var(--text-dim)]",
            )}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="num ml-1.5 text-[13px] text-[var(--color-st-rejected)]">
                {t.count}
              </span>
            )}
            <span
              className={cn(
                "absolute inset-x-2 bottom-0 h-[2px]",
                tab === t.id ? "bg-[var(--accent)]" : "bg-transparent",
              )}
            />
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "alerts" ? <AdminAlerts /> : <AdminPreparedness />}
      </div>
    </AppShell>
  );
}
