import { Network } from "lucide-react";
import { useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { useNavigate } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
import { Skeleton } from "@/components/ui/skeleton";
import type { RingInfo } from "@/lib/types";

const BAND_COLORS: Record<string, string> = {
  AUTO_APPROVE: "#6EA335",
  HUMAN_REVIEW: "#FEB12B",
  AUTO_FLAG: "#B81514",
};
const SELF_COLOR = "#3333CC";
const HISTORICAL_COLOR = "#B3B3B3";

export function RingPanel({
  ring,
  loading,
  error,
}: {
  ring: RingInfo | null;
  loading: boolean;
  error: string | null;
}) {
  const navigate = useNavigate();

  const graphData = useMemo(() => {
    if (!ring || ring.ring_size === 0) return { nodes: [], links: [] };
    const nodes = [
      { id: ring.application_id, label: "THIS APPLICATION", color: SELF_COLOR, val: 7, self: true, band: null as string | null, source: "database" },
      ...ring.members.map((m) => ({
        id: m.application_id,
        label: `${m.application_id.slice(0, 8)}… ${m.decision_band ?? "(historical)"}`,
        color: m.decision_band ? BAND_COLORS[m.decision_band] : HISTORICAL_COLOR,
        val: 3,
        self: false,
        band: m.decision_band as string | null,
        source: m.source,
      })),
    ];
    const links = ring.members.map((m) => ({
      source: ring.application_id,
      target: m.application_id,
    }));
    return { nodes, links };
  }, [ring]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>
          <TitleIcon icon={Network} tone="danger" />
          Fraud ring analysis
        </CardTitle>
        {ring && ring.ring_size > 0 && (
          <span className="text-sm">
            <span className="text-muted-foreground">ring risk </span>
            <span
              className={`font-semibold tabular-nums ${
                ring.ring_risk_score >= 0.5 ? "text-danger" : "text-brand"
              }`}
            >
              {(ring.ring_risk_score * 100).toFixed(0)}%
            </span>
          </span>
        )}
      </CardHeader>
      <CardContent>
        {loading && <Skeleton className="h-48 w-full" />}
        {error && <p className="text-sm text-danger">Ring lookup unavailable — {error}</p>}
        {!loading && !error && ring && ring.ring_size === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No connections found — this application is not linked to any others by device or IP.
          </p>
        )}
        {!loading && !error && ring && ring.ring_size > 0 && (
          <>
            <p className="mb-2 text-sm text-muted-foreground">
              Connected to <span className="text-foreground">{ring.members.length}</span> other
              application{ring.members.length === 1 ? "" : "s"} through a shared device
              fingerprint or IP address.
            </p>
            <div className="overflow-hidden rounded-md border border-border bg-background/60">
              <ForceGraph2D
                graphData={graphData}
                width={640}
                height={280}
                backgroundColor="rgba(0,0,0,0)"
                nodeLabel="label"
                nodeColor={(n: any) => n.color}
                nodeVal={(n: any) => n.val}
                linkColor={() => "#CCCCCC"}
                linkWidth={1.2}
                enableZoomInteraction={false}
                cooldownTicks={60}
                onNodeClick={(node: any) => {
                  if (!node.self && node.source === "database")
                    navigate(`/applications/${node.id}`);
                }}
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: SELF_COLOR }} />this application</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-danger" />auto-flagged</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-warning" />human review</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-success" />auto-approved</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: HISTORICAL_COLOR }} />historical record</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
