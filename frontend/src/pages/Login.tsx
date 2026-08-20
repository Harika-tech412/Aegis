import { AlertCircle, Gauge, Layers, Network, ShieldCheck, Target } from "lucide-react";
import { useState, type FormEvent } from "react";

import GradientWaves from "@/components/reactbits/GradientWaves";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";

// Representative metrics from the model report — talking points that plant
// credibility while the presenter signs in.
const GLANCE_STATS = [
  { icon: Layers, value: "18,000+", label: "synthetic applications analyzed" },
  { icon: Gauge, value: "126ms", label: "average scoring latency" },
  { icon: Network, value: "6", label: "signal modalities fused" },
  { icon: Target, value: "0.97", label: "PR-AUC on shifted holdout" },
];

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  // Demo build: credentials pre-filled so the presenter clicks straight through.
  const [username, setUsername] = useState("investigator");
  const [password, setPassword] = useState("aegis_demo_2026");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate("/dashboard");
    } catch {
      // Deliberately vague — never reveal whether username or password failed.
      setError("Sign-in failed. Verify credentials with your administrator.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* ---- Left brand panel (hidden under 768px) ---- */}
      <div className="relative hidden w-3/5 flex-col justify-center overflow-hidden border-r border-border bg-[#070E1A] p-10 lg:p-14 md:flex">
        {/* Animated background, hero panel only — never the form panel, never
            full-page. Falls back to a CSS gradient if WebGL is unavailable. */}
        <div className="absolute inset-0 z-0">
          <GradientWaves />
        </div>
        <div className="pointer-events-none absolute inset-0 z-[1] bg-gradient-to-r from-[#070E1A]/70 via-[#070E1A]/40 to-[#070E1A]/75" />
        <div className="relative z-10 flex items-center gap-2.5">
          <ShieldCheck className="h-6 w-6 text-brand" />
          <span className="text-lg font-semibold tracking-tight text-slate-100">Aegis</span>
        </div>

        <div className="relative z-10 max-w-xl">
          <h1 className="text-[2.5rem] font-bold leading-[1.12] tracking-tight text-foreground">
            Every application has a story.
            <br />
            Aegis makes sure it&rsquo;s the true one.
          </h1>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-brand">
            Real-time trust intelligence for digital lending
          </p>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-muted-foreground">
            Multi-signal fraud detection with explainable decisioning, fraud-ring graph
            analysis, and a human investigator always in the loop.
          </p>

          <div className="mt-8 grid grid-cols-4 gap-2">
            {GLANCE_STATS.map(({ icon: Icon, value, label }) => (
              <div
                key={label}
                className="rounded-lg border border-border bg-card/50 px-3 py-2.5"
              >
                <Icon className="mb-1.5 h-3.5 w-3.5 text-brand/70" strokeWidth={2} />
                <p className="text-base font-bold tabular-nums leading-none text-foreground">
                  {value}
                </p>
                <p className="mt-1 text-[10px] leading-tight text-subtle">{label}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="absolute bottom-8 left-10 z-10 text-[11px] text-slate-400/80 lg:left-14">
          Demonstration environment · all data is synthetic · Synchrony Hackathon 2026
        </p>
      </div>

      {/* ---- Right login panel ---- */}
      <div className="flex w-full flex-col items-center justify-center px-6 md:w-2/5">
        {/* compact logo strip for small screens where the brand panel is hidden */}
        <div className="mb-8 flex items-center gap-2 md:hidden">
          <ShieldCheck className="h-5 w-5 text-brand" />
          <span className="text-lg font-semibold">Aegis</span>
          <span className="text-xs uppercase tracking-widest text-muted-foreground">
            Trust Intelligence
          </span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <div className="icon-chip icon-chip-brand mb-4 !p-3">
              <ShieldCheck className="h-6 w-6" strokeWidth={2} />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">AEGIS</h2>
            <p className="mt-1 text-sm text-muted-foreground">Investigator Console</p>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground md:hidden">
              Every application has a story. Aegis makes sure it&rsquo;s the true one.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {error && (
              <div className="flex items-start gap-2.5 rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="mt-3 text-center text-xs text-subtle">
            Demo credentials pre-filled — click <span className="font-medium text-muted-foreground">Sign in</span> to continue.
          </p>

          <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
            Not an investigator? Access is provisioned by your IT administrator.
            <br />
            <a href="/apply" className="mt-1 inline-block text-brand/90 hover:underline">
              Apply for a loan →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
