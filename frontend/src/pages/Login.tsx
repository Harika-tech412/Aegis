import { AlertCircle, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import GradientWaves from "@/components/reactbits/GradientWaves";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";

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
      <div className="relative hidden w-3/5 flex-col justify-center overflow-hidden border-r border-border bg-secondary p-10 lg:p-14 md:flex">
        {/* Animated background, hero panel only — never the form panel, never
            full-page. Falls back to a CSS gradient if WebGL is unavailable. */}
        <div className="absolute inset-0 z-0">
          <GradientWaves />
        </div>
        {/* Paper-side scrim: keeps text contrast without dimming to grey. */}
        <div className="pointer-events-none absolute inset-0 z-[1] bg-gradient-to-r from-secondary/80 via-secondary/55 to-secondary/85" />
        <div className="relative z-10 flex items-center gap-2.5">
          <ShieldCheck className="h-6 w-6 text-brand" />
          <span className="text-lg font-semibold tracking-tight text-foreground">Aegis</span>
        </div>

        <div className="relative z-10 max-w-xl">
          <h1 className="text-[2.5rem] font-bold leading-[1.12] tracking-tight text-foreground">
            Every application has a story.
            <br />
            Aegis makes sure it&rsquo;s the true one.
          </h1>
        </div>

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
            <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
            <p className="mt-1 text-sm text-muted-foreground">Investigator console</p>
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
            Demo credentials pre-filled — just sign in.
          </p>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            <a href="/apply" className="text-brand hover:underline">
              Apply for a loan →
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
