import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/store/auth";

const DEMO = [
  { email: "admin@demo.in", password: "admin123", role: "Admin" },
  { email: "verifier@demo.in", password: "verifier123", role: "Verifier" },
  { email: "analyst@demo.in", password: "analyst123", role: "Analyst" },
];

export function Login() {
  const navigate = useNavigate();
  const login = useAuth((s) => s.login);
  const [email, setEmail] = React.useState("verifier@demo.in");
  const [password, setPassword] = React.useState("verifier123");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      navigate(user.role === "PUBLIC_USER" ? "/" : "/admin");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const field =
    "h-10 w-full rounded-[var(--r-sm)] border border-[var(--hairline)] bg-[var(--veil-1)] px-3 text-sm text-[var(--text-ink)] transition-colors placeholder:text-[var(--text-faint)] focus:border-[var(--color-accent)]/45 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/30";

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="panel rise w-full max-w-[400px] rounded-[var(--r-xl)] p-7">
        <div className="mb-6 flex items-center gap-3">
          <img
            src="/logo-mark.png"
            alt=""
            width={52}
            height={52}
            className="h-13 w-13 shrink-0 select-none"
            draggable={false}
          />
          <div>
            <div className="text-[15px] font-semibold tracking-[-0.015em]">National Weather Analytics</div>
            <div className="mt-1.5 text-[12.5px] text-[var(--text-faint)]">Operator sign in</div>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="label mb-1.5 block">Email</label>
            <input className={field} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label mb-1.5 block">Password</label>
            <input
              type="password"
              className={field}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <div className="rise rounded-[var(--r-sm)] border border-[var(--color-st-rejected)]/35 bg-[var(--color-st-rejected)]/10 px-3 py-2 text-[13px] text-[var(--color-st-rejected)]">
              {error}
            </div>
          )}
          <Button type="submit" variant="default" size="lg" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 border-t border-[var(--hairline-soft)] pt-4">
          <div className="label mb-2">Demo accounts</div>
          <div className="space-y-1.5">
            {DEMO.map((d) => (
              <button
                key={d.email}
                onClick={() => {
                  setEmail(d.email);
                  setPassword(d.password);
                }}
                className="flex w-full items-center justify-between rounded-[var(--r-sm)] border border-[var(--hairline-soft)] bg-[var(--veil-2)] px-2.5 py-1.5 text-left transition-all duration-150 hover:border-[var(--hairline)] hover:bg-[var(--veil-1)]"
              >
                <span className="num text-[13px] text-[var(--text-dim)]">{d.email}</span>
                <span className="label-caps">{d.role}</span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-[12.5px] leading-relaxed text-[var(--text-faint)]">
            The public dashboard needs no account. Sign in to triage the verification
            queue and manage sources.
          </p>
        </div>
      </div>
    </div>
  );
}
