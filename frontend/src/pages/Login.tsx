import { AlertCircle, Gauge, Layers, Network, ShieldCheck, Target } from "lucide-react";
import { useState, type FormEvent } from "react";
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
      <div className="relative hidden w-3/5 flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0a1428] via-[#0c1a33] to-[#111f3d] p-10 md:flex">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="h-6 w-6 text-amber-400" />
          <span className="text-lg font-semibold tracking-tight text-slate-100">Aegis</span>
        </div>

        <div className="max-w-lg">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-slate-100">
            Real-time trust intelligence for digital lending.
          </h1>
          <p className="mt-4 text-base leading-relaxed text-slate-400">
            Multi-signal fraud detection with explainable decisioning, fraud-ring graph
            analysis, and a human investigator always in the loop.
          </p>

          <div className="mt-10 grid grid-cols-2 gap-3">
            {GLANCE_STATS.map(({ icon: Icon, value, label }) => (
              <div
                key={label}
                className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-4"
              >
                <Icon className="mb-2 h-4 w-4 text-amber-400/80" />
                <p className="text-xl font-semibold tabular-nums text-slate-100">{value}</p>
                <p className="mt-0.5 text-xs text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-slate-600">
          Demonstration environment · all data is synthetic · Synchrony Hackathon 2026
        </p>
      </div>

      {/* ---- Right login panel ---- */}
      <div className="flex w-full flex-col items-center justify-center px-6 md:w-2/5">
        {/* compact logo strip for small screens where the brand panel is hidden */}
        <div className="mb-8 flex items-center gap-2 md:hidden">
          <ShieldCheck className="h-5 w-5 text-amber-400" />
          <span className="text-lg font-semibold">Aegis</span>
          <span className="text-xs uppercase tracking-widest text-muted-foreground">
            Trust Intelligence
          </span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-border bg-secondary">
              <ShieldCheck className="h-7 w-7 text-amber-400" />
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">Aegis</h2>
            <p className="mt-1 text-sm text-muted-foreground">Investigator Console</p>
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
              <div className="flex items-start gap-2.5 rounded-md border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-4 rounded-md border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300/90">
            Demo credentials pre-filled — click <span className="font-semibold">Sign in</span> to
            continue.
          </div>

          <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">
            Not an investigator? Access is provisioned by your IT administrator.
            <br />
            <a href="/apply" className="mt-1 inline-block text-amber-400/90 hover:underline">
              Apply for a loan →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
