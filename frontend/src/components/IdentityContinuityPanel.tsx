/**
 * Layer 5 — identity continuity and step-up outcome.
 *
 * Reuses the existing Card/TitleIcon pattern; no new visual language. Tone
 * follows the established colour contract: warning amber for "a human should
 * look at this", danger red for a failed challenge, success green for a passed
 * one, muted for no history.
 */

import { History, ShieldCheck, ShieldX } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
import type { IdentityContinuity, StepUpResult } from "@/lib/types";

const STATUS_COPY: Record<string, string> = {
  NO_HISTORY: "No prior application on file for this identity",
  CONSISTENT: "Matches this identity's established pattern",
  INCONSISTENT: "Diverges from this identity's established pattern",
};

export function IdentityContinuityPanel({
  continuity,
  stepUp,
}: {
  continuity: IdentityContinuity | null | undefined;
  stepUp: StepUpResult | null | undefined;
}) {
  if (!continuity) return null;

  const inconsistent = continuity.status === "INCONSISTENT";
  const statusTone = inconsistent ? "text-warning" : "text-muted-foreground";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <TitleIcon icon={History} tone={inconsistent ? "warning" : "brand"} />
          Identity Continuity
        </CardTitle>
        <p className="aegis-section-desc mt-1">
          This identity&rsquo;s current application against its own history
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={`text-sm font-bold tracking-tight ${statusTone}`}>
            {continuity.status.replace("_", " ")}
          </span>
          <span className="text-sm text-muted-foreground">
            {STATUS_COPY[continuity.status] ?? continuity.detail}
          </span>
        </div>

        <p className="text-xs text-subtle">
          {continuity.prior_observations} prior observation
          {continuity.prior_observations === 1 ? "" : "s"} on file
          {continuity.baseline_observations
            ? ` · baseline drawn from the earliest ${continuity.baseline_observations}`
            : ""}
        </p>

        {continuity.changed_signals.length > 0 && (
          <ul className="space-y-1">
            {continuity.changed_signals.map((signal) => (
              <li key={signal} className="flex gap-2 text-sm text-foreground">
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                <span>{signal}</span>
              </li>
            ))}
          </ul>
        )}

        {inconsistent && !stepUp && (
          <p className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-muted-foreground">
            Eligible for out-of-band step-up verification. Divergence alone does not change the
            decision — only the challenge result does.
          </p>
        )}

        {stepUp && (
          <div
            className={`rounded-md border p-3 ${
              stepUp.outcome === "CORRECT"
                ? "border-success/40 bg-success/10"
                : "border-danger/40 bg-danger/10"
            }`}
          >
            <div className="flex items-center gap-2">
              {stepUp.outcome === "CORRECT" ? (
                <ShieldCheck className="h-4 w-4 text-success" strokeWidth={2} />
              ) : (
                <ShieldX className="h-4 w-4 text-danger" strokeWidth={2} />
              )}
              <p
                className={`text-xs font-bold uppercase tracking-wider ${
                  stepUp.outcome === "CORRECT" ? "text-success" : "text-danger"
                }`}
              >
                Step-up {stepUp.outcome === "CORRECT" ? "passed" : "failed"}
              </p>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              Code sent to the contact on file ({stepUp.masked_contact}) was answered{" "}
              {stepUp.outcome === "CORRECT" ? "correctly" : "incorrectly"}.
            </p>
            <p className="mt-1 text-xs tabular-nums text-subtle">
              risk {stepUp.risk_before.toFixed(3)} → {stepUp.risk_after.toFixed(3)} (
              {stepUp.risk_delta > 0 ? "+" : ""}
              {stepUp.risk_delta.toFixed(2)}) · band {stepUp.band_before} → {stepUp.band_after}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
