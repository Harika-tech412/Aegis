import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { DriftResponse } from "@/lib/types";

function psiColor(psi: number): string {
  if (psi > 0.25) return "#ef4444";
  if (psi > 0.1) return "#f59e0b";
  return "#10b981";
}

/** One short sentence for the collapsed view (the API summary is a paragraph). */
function shortSummary(drift: DriftResponse): string {
  const n = drift.recent_applications;
  const apps = `${n} application${n === 1 ? "" : "s"}`;
  if (drift.overall_drift_status === "INSUFFICIENT_DATA")
    return `Only ${apps} in the last ${drift.window_hours}h — 30 needed for a PSI verdict.`;
  const drifted = drift.features.filter((f) => f.status !== "STABLE").length;
  if (drift.overall_drift_status === "STABLE")
    return `Input distributions match training data across ${apps}.`;
  return `${drifted} of ${drift.features.length} features drifting across ${apps}.`;
}

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
  // Collapsed on every page load by design — details are opt-in, not sticky.
  const [expanded, setExpanded] = useState(false);

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

            {/* Collapsed by default: one status line + one short sentence. The
                per-feature PSI bars and the full explanation are opt-in. */}
            <p className="text-sm leading-relaxed text-muted-foreground">{shortSummary(drift)}</p>

            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {expanded ? "Hide details" : "Show details"}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
              />
            </button>

            {expanded && (
              <p className="border-t border-border pt-2.5 text-sm leading-relaxed text-muted-foreground">
                {drift.summary}
              </p>
            )}
            {expanded && drift.features.length > 0 && (
              <div className="h-40 w-full pt-1">
                <ResponsiveContainer>
                  <BarChart
                    data={drift.features.slice(0, 6).map((f) => ({
                      name: f.feature.replace(/_/g, " ").replace("applications from", "apps"),
                      psi: f.psi,
                    }))}
                    layout="vertical"
                    margin={{ left: 4, right: 16, top: 0, bottom: 0 }}
                  >
                    <XAxis
                      type="number"
                      tick={{ fill: "#64748b", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={130}
                      tick={{ fill: "#94a3b8", fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <ReferenceLine x={0.25} stroke="#7f1d1d" strokeDasharray="3 3" />
                    <Tooltip
                      cursor={{ fill: "rgba(148,163,184,0.06)" }}
                      contentStyle={{
                        background: "#0f172a",
                        border: "1px solid #1e293b",
                        borderRadius: 6,
                        fontSize: 11,
                      }}
                      formatter={(v: number) => [v.toFixed(3), "PSI"]}
                    />
                    <Bar dataKey="psi" barSize={10} radius={[2, 2, 2, 2]}>
                      {drift.features.slice(0, 6).map((f) => (
                        <Cell key={f.feature} fill={psiColor(f.psi)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
