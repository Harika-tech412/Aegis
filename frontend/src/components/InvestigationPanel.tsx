import { Bot, CheckCircle2, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
import { api } from "@/lib/api";
import type { InvestigationResponse } from "@/lib/types";
import { formatTime } from "@/lib/utils";

// Confidence is agent-scoped: HIGH reads solid, MEDIUM/LOW lighter.
const CONFIDENCE_STYLE: Record<string, "agent" | "outline"> = {
  HIGH: "agent",
  MEDIUM: "outline",
  LOW: "outline",
};

const STEP_LABELS: Record<string, string> = {
  triage: "Triage",
  quick_exit: "Triage — early exit",
  check_ring: "Fraud-ring lookup",
  check_ring_feedback: "Ring feedback history",
  check_similar_cases: "Similar past cases",
  check_drift: "Model drift check",
  synthesize: "Synthesis",
};

/** Stagger between revealed steps (ms). */
const STEP_DELAY = 400;

export function InvestigationPanel({ applicationId }: { applicationId: string }) {
  const [data, setData] = useState<InvestigationResponse | null>(null);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  async function run(refresh = false) {
    setBusy(true);
    setError(null);
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setVisibleSteps(0);
    try {
      const result = await api.investigate(applicationId, refresh);
      setData(result);

      // The API call has already completed by this point — the steps are
      // revealed one at a time purely so the reasoning is legible as a
      // sequence rather than dumping as a wall of text. A deliberate UX
      // choice to make the agent's chain of reasoning followable, not a
      // simulation of latency.
      result.investigation_log.forEach((_, i) => {
        timers.current.push(
          window.setTimeout(() => setVisibleSteps(i + 1), i * STEP_DELAY)
        );
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const allRevealed = data !== null && visibleSteps >= data.investigation_log.length;

  return (
    <Card className="border-agent/35">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>
          <TitleIcon icon={Bot} tone="agent" />
          AI Investigation Agent
        </CardTitle>
        {data && (
          <div className="flex items-center gap-2">
            {data.cached && (
              <span className="text-xs text-muted-foreground">
                Cached from {formatTime(data.created_at)}
              </span>
            )}
            <Button variant="ghost" size="sm" onClick={() => run(true)} disabled={busy}>
              <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Re-run
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {!data && !error && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Run a multi-step agent that decides for itself which checks this case warrants —
              ring links, prior verdicts on connected applications, similar cases, and drift.
            </p>
            <Button onClick={() => run(false)} disabled={busy}>
              {busy ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Investigating…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" /> Run agent investigation
                </>
              )}
            </Button>
          </div>
        )}

        {error && (
          <p className="text-sm text-danger">Investigation unavailable — {error}</p>
        )}

        {data && (
          <div className="space-y-4">
            <ol className="space-y-2">
              {data.investigation_log.slice(0, visibleSteps).map((entry, i) => (
                <li
                  key={`${entry.step}-${i}`}
                  className="flex animate-feed-in items-start gap-3 rounded-lg border border-border bg-background/40 p-3"
                >
                  <CheckCircle2
                    className="mt-0.5 h-5 w-5 shrink-0 text-agent"
                    strokeWidth={2.25}
                    aria-label={`step ${i + 1} complete`}
                  />
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-agent">
                      {STEP_LABELS[entry.step] ?? entry.step}
                    </p>
                    <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
                      {entry.description}
                    </p>
                  </div>
                </li>
              ))}
              {!allRevealed && (
                <li className="flex items-center gap-2 px-3 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" /> reasoning…
                </li>
              )}
            </ol>

            {allRevealed && (
              <div className="animate-feed-in rounded-lg border border-agent/40 border-l-4 border-l-agent bg-agent/5 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <Sparkles className="h-4 w-4 text-agent" strokeWidth={2} />
                    Recommended action
                  </p>
                  <Badge variant={CONFIDENCE_STYLE[data.confidence] ?? "default"}>
                    {data.confidence} CONFIDENCE
                  </Badge>
                </div>
                <p className="mt-2 text-base font-bold tracking-tight text-foreground">
                  {data.recommended_action}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {data.reasoning_summary}
                </p>
                <p className="mt-3 text-xs text-muted-foreground">
                  {data.investigation_log.length} step
                  {data.investigation_log.length === 1 ? "" : "s"} ·{" "}
                  {data.synthesis_source === "groq"
                    ? "synthesis by language model"
                    : data.synthesis_source === "quick_exit"
                      ? "early exit — no synthesis needed"
                      : "deterministic synthesis"}
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
