import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { DriftResponse } from "@/lib/types";

const STATUS_STYLE: Record<string, { dot: string; text: string; label: string }> = {
  STABLE: { dot: "bg-emerald-400", text: "text-emerald-400", label: "Stable" },
  MILD_DRIFT: { dot: "bg-amber-400", text: "text-amber-400", label: "Mild drift" },
  SIGNIFICANT_DRIFT: { dot: "bg-red-400", text: "text-red-400", label: "Significant drift" },
  INSUFFICIENT_DATA: {
    dot: "bg-slate-500",
    text: "text-muted-foreground",
    label: "Insufficient data",
  },
};

export function DriftWidget() {
  const [drift, setDrift] = useState<DriftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .getDrift(24)
        .then((d) => !cancelled && (setDrift(d), setError(null)))
        .catch((e) => !cancelled && setError((e as Error).message));
    load();
    const timer = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const style = drift ? STATUS_STYLE[drift.overall_drift_status] : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Model drift — last 24h (PSI)</CardTitle>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-red-400">Drift monitor unavailable — {error}</p>}
        {!error && !drift && <Skeleton className="h-16 w-full" />}
        {!error && drift && style && (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
              <span className={`text-base font-semibold ${style.text}`}>{style.label}</span>
              <span className="text-xs text-muted-foreground">
                {drift.recent_applications} application
                {drift.recent_applications === 1 ? "" : "s"} in window
              </span>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{drift.summary}</p>
            {drift.features.length > 0 && (
              <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-xs text-muted-foreground">
                {drift.features.slice(0, 4).map((f) => (
                  <span key={f.feature} className="tabular-nums">
                    {f.feature.replace(/_/g, " ")}: {f.psi.toFixed(2)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
