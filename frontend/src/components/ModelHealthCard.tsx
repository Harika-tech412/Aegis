import { Activity, ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TitleIcon } from "@/components/ui/title-icon";
import { api } from "@/lib/api";
import type { DriftFeature, DriftResponse } from "@/lib/types";

/**
 * Signal families for the headline breakdown.
 *
 * The three buckets cover the fraud-relevant signal families an investigator
 * reasons about. `applicant_age`, `annual_income` and `requested_amount` are
 * application-profile inputs rather than integrity signals, so they are
 * excluded from the headline rows but remain in the full PSI breakdown below.
 */
const BUCKETS: { label: string; features: string[] }[] = [
  {
    label: "Identity signals",
    features: ["identity_consistency_score", "income_employer_consistency_score"],
  },
  {
    label: "Behavioral signals",
    features: ["session_duration_seconds", "mouse_movement_events", "form_paste_count"],
  },
  {
    label: "Network signals",
    features: ["applications_from_device_last_24h", "applications_from_ip_last_24h"],
  },
];

/**
 * PSI -> health percentage.
 *
 *   health = 100 * (1 - mean(PSI) / 0.5)
 *
 * Anchored to the industry PSI bands already used by the backend: mean PSI 0
 * reads 100% (distributions identical to training), 0.10 (the "mild drift"
 * line) reads 80%, 0.25 ("significant") reads 50%, and 0.50+ floors at 0%.
 * Clamped to [0, 100].
 */
function healthFromPsi(features: DriftFeature[]): number | null {
  if (!features.length) return null;
  const mean = features.reduce((sum, f) => sum + f.psi, 0) / features.length;
  return Math.max(0, Math.min(100, Math.round(100 * (1 - mean / 0.5))));
}

function bucketHealth(features: DriftFeature[], names: string[]): number | null {
  return healthFromPsi(features.filter((f) => names.includes(f.feature)));
}

const STATUS = {
  STABLE: { label: "Healthy", ring: "#22C55E", text: "text-success", dot: "bg-success" },
  MILD_DRIFT: { label: "Monitor", ring: "#F59E0B", text: "text-warning", dot: "bg-warning" },
  SIGNIFICANT_DRIFT: {
    label: "Significant Drift",
    ring: "#EF4444",
    text: "text-danger",
    dot: "bg-danger",
  },
  INSUFFICIENT_DATA: {
    label: "Awaiting data",
    ring: "#64748B",
    text: "text-muted-foreground",
    dot: "bg-subtle",
  },
} as const;

function toneFor(health: number | null): string {
  if (health === null) return "bg-subtle";
  if (health >= 80) return "bg-success";
  if (health >= 50) return "bg-warning";
  return "bg-danger";
}

/** Hand-rolled SVG arc gauge — no chart library sizing quirks to fight. */
function Gauge({ percent, color }: { percent: number | null; color: string }) {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const shown = percent ?? 0;
  // 300-degree sweep leaves a visual gap at the bottom of the dial.
  const sweep = 0.833;
  const dash = (shown / 100) * circumference * sweep;

  return (
    <div className="relative h-[124px] w-[124px] shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-[150deg]">
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${circumference * sweep} ${circumference}`}
        />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          style={{ transition: "stroke-dasharray 600ms cubic-bezier(0.22,1,0.36,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[26px] font-bold tabular-nums leading-none text-foreground">
          {percent === null ? "—" : `${percent}%`}
        </span>
        <span className="aegis-overline mt-0.5">health</span>
      </div>
    </div>
  );
}

export function ModelHealthCard() {
  const [drift, setDrift] = useState<DriftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  const status = drift ? STATUS[drift.overall_drift_status] : null;
  const health = drift ? healthFromPsi(drift.features) : null;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>
          <TitleIcon icon={Activity} tone="brand" />
          Model Health
        </CardTitle>
        <span className="aegis-overline">24h window</span>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-danger">Monitor unavailable — {error}</p>}
        {!error && !drift && <Skeleton className="h-28 w-full" />}

        {!error && drift && status && (
          <div className="space-y-4">
            <div className="flex items-center gap-5">
              <Gauge percent={health} color={status.ring} />
              <div className="min-w-0 flex-1">
                <p className={`text-lg font-bold tracking-tight ${status.text}`}>{status.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {drift.recent_applications} application
                  {drift.recent_applications === 1 ? "" : "s"} scored
                </p>

                <div className="mt-3 space-y-1.5">
                  {BUCKETS.map((bucket) => {
                    const value = bucketHealth(drift.features, bucket.features);
                    return (
                      <div key={bucket.label} className="flex items-center gap-2 text-xs">
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${toneFor(value)}`} />
                        <span className="flex-1 truncate text-muted-foreground">
                          {bucket.label}
                        </span>
                        <span className="tabular-nums text-foreground">
                          {value === null ? "—" : `${value}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex w-full items-center justify-between border-t border-border pt-2.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              View model details
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
              />
            </button>

            {expanded && (
              <div className="space-y-2">
                <p className="aegis-body">{drift.summary}</p>
                {drift.features.length > 0 && (
                  <div className="h-40 w-full">
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
                            borderRadius: 8,
                            fontSize: 11,
                          }}
                          formatter={(v: number) => [v.toFixed(3), "PSI"]}
                        />
                        <Bar dataKey="psi" barSize={10} radius={[2, 2, 2, 2]}>
                          {drift.features.slice(0, 6).map((f) => (
                            <Cell
                              key={f.feature}
                              fill={f.psi > 0.25 ? "#EF4444" : f.psi > 0.1 ? "#F59E0B" : "#22C55E"}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <p className="text-[11px] text-muted-foreground">
                  Population Stability Index per feature · PSI &lt; 0.10 stable · 0.10–0.25 mild ·
                  &gt; 0.25 significant
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
