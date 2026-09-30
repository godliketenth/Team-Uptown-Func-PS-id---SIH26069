import * as React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Monitor } from "@/pages/Monitor";
import { Verify } from "@/pages/Verify";
import { Advise } from "@/pages/Advise";
import { Login } from "@/pages/Login";
import { AdminShell } from "@/pages/admin/AdminShell";
import { AdminSources } from "@/pages/admin/AdminSources";
import { AdminCredibility } from "@/pages/admin/AdminCredibility";
import { AdminReports } from "@/pages/admin/AdminReports";
import { AdminEvents } from "@/pages/admin/AdminEvents";
import { AdminHealth } from "@/pages/admin/AdminHealth";
import { AdminAudit } from "@/pages/admin/AdminAudit";
import { useAuth } from "@/store/auth";

/**
 * Three operational modes, plus a system area.
 *
 * Monitor, Verify and Advise are the three jobs this platform exists to do,
 * and each has a screen built for it. `/admin` keeps what is genuinely
 * administration — collector configuration, raw reports, pipeline telemetry,
 * the audit trail — rather than being where the real work was hidden.
 *
 * The alert queue moved into Advise, and the verification queue into Verify,
 * so neither is reachable at its old `/admin` path; both redirect rather than
 * 404, because those links have been shared.
 */
export default function App() {
  const restore = useAuth((s) => s.restore);

  React.useEffect(() => {
    void restore();
  }, [restore]);

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/monitor" replace />} />
      <Route path="/monitor" element={<Monitor />} />
      {/* Deep link opens Monitor with the event's slide-over, so an event
          stays shareable. */}
      <Route path="/events/:eventId" element={<Monitor />} />
      <Route path="/verify" element={<Verify />} />
      <Route path="/advise" element={<Advise />} />
      <Route path="/login" element={<Login />} />

      <Route path="/admin" element={<AdminShell />}>
        <Route index element={<Navigate to="/admin/sources" replace />} />
        <Route path="sources" element={<AdminSources />} />
        <Route path="credibility" element={<AdminCredibility />} />
        <Route path="reports" element={<AdminReports />} />
        <Route path="events" element={<AdminEvents />} />
        <Route path="health" element={<AdminHealth />} />
        <Route path="audit" element={<AdminAudit />} />
      </Route>

      {/* Moved, not removed. */}
      <Route path="/admin/alerts" element={<Navigate to="/advise" replace />} />
      <Route path="/admin/preparedness" element={<Navigate to="/advise" replace />} />
      <Route path="/admin/verification" element={<Navigate to="/verify" replace />} />

      <Route path="*" element={<Navigate to="/monitor" replace />} />
    </Routes>
  );
}
