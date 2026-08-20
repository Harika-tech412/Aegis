/**
 * Aegis Network — cross-institution fraud intelligence.
 *
 * The network accent is cyan throughout: distinct from brand blue (our own
 * interactive colour), from amber/red (our own detections), and from violet
 * (the AI agent). Cyan means "this came from outside this institution".
 */

import { Building2, Radio, ShieldCheck, Share2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

import { Navbar } from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TitleIcon } from "@/components/ui/title-icon";
import { api } from "@/lib/api";
import { stagger } from "@/lib/motion";
import type { NetworkGraph, NetworkSignalsResponse, NetworkStats } from "@/lib/types";
import { formatTime } from "@/lib/utils";

const CYAN = "#0E7490"; // cyan-700 — legible on paper

const HOW_IT_WORKS = [
  "Each institution scores applications independently, on its own data and its own models.",
  "When an investigator confirms fraud, one-way cryptographic hashes of the device fingerprint and network address are published to the Aegis Network.",
  "Partner institutions receiving new applications automatically check incoming signals against network hashes.",
  "A match raises the risk score and names the reporting institution, so the analyst knows the evidence is external.",
  "No names, no identifiers, no PII crosses institutional boundaries — only salted digests that cannot be reversed.",
];

function StatTile({
  icon: Icon,
  label,
  value,
  index,
}: {
  icon: typeof Building2;
  label: string;
  value: number | null;
  index: number;
}) {
  return (
    <Card className="aegis-enter aegis-surface-hover" style={stagger(index)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="aegis-label leading-tight">{label}</p>
          <span
            className="icon-chip"
            style={{ background: "rgba(14,116,144,0.08)", color: CYAN }}
          >
            <Icon className="h-4 w-4" strokeWidth={2} />
          </span>
        </div>
        {value === null ? (
          <Skeleton className="mt-2 h-8 w-16" />
        ) : (
          <p className="aegis-metric mt-2" style={{ color: CYAN }}>
            {value.toLocaleString()}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export function NetworkPage() {
  const [stats, setStats] = useState<NetworkStats | null>(null);
  const [signals, setSignals] = useState<NetworkSignalsResponse | null>(null);
  const [graph, setGraph] = useState<NetworkGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getNetworkStats(), api.getNetworkSignals(20), api.getNetworkGraph()])
      .then(([s, sig, g]) => {
        if (cancelled) return;
        setStats(s);
        setSignals(sig);
        setGraph(g);
      })
      .catch((e) => !cancelled && setError((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, []);

  // With two members this is a single edge. If no cross-institution hit has
  // occurred yet there is no edge at all — we draw a dashed "no traffic yet"
  // placeholder rather than an empty canvas.
  const graphData = useMemo(() => {
    if (!graph) return { nodes: [], links: [] };
    return {
      nodes: graph.nodes.map((n) => ({
        id: n.id,
        label: `${n.label} · ${n.signals_published} signals`,
        published: n.signals_published,
      })),
      links: graph.links.map((l) => ({
        source: l.source,
        target: l.target,
        hits: l.shared_signal_hits,
      })),
    };
  }, [graph]);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl space-y-4 px-4 py-5 sm:px-6">
        <div className="aegis-enter">
          <p className="aegis-overline" style={{ color: CYAN }}>
            Cross-institution intelligence
          </p>
          <h1 className="aegis-title mt-1">Aegis Network</h1>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            Confirmed fraud signals shared across member institutions as one-way
            cryptographic hashes. No customer identity data leaves any bank.
          </p>
        </div>

        {error && (
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-danger">Network unavailable — {error}</p>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile icon={Building2} label="Member institutions" value={stats?.member_institutions ?? null} index={0} />
          <StatTile icon={Share2} label="Signals in network" value={stats?.total_signals ?? null} index={1} />
          <StatTile icon={Radio} label="Published (24h)" value={stats?.signals_last_24h ?? null} index={2} />
          <StatTile icon={ShieldCheck} label="Prevented attacks" value={stats?.prevented_attacks ?? null} index={3} />
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {/* ---- Graph ---- */}
          <Card className="aegis-enter xl:col-span-2" style={stagger(4)}>
            <CardHeader>
              <CardTitle>
                <TitleIcon icon={Share2} tone="brand" />
                Member topology
              </CardTitle>
              <p className="aegis-section-desc mt-1">
                Edge thickness reflects how many partner signals have matched applications
                scored by the receiving institution.
              </p>
            </CardHeader>
            <CardContent>
              {!graph ? (
                <Skeleton className="h-64 w-full" />
              ) : (
                <>
                  <div className="overflow-hidden rounded-lg border border-border bg-background/60">
                    <ForceGraph2D
                      graphData={graphData}
                      width={620}
                      height={260}
                      backgroundColor="rgba(0,0,0,0)"
                      nodeLabel="label"
                      nodeVal={(n: any) => 6 + Math.min(n.published, 40) / 4}
                      nodeColor={() => CYAN}
                      linkColor={() => "rgba(14,116,144,0.45)"}
                      linkWidth={(l: any) => 1 + Math.min(l.hits, 20) * 0.6}
                      linkDirectionalParticles={2}
                      linkDirectionalParticleWidth={2}
                      enableZoomInteraction={false}
                      cooldownTicks={60}
                    />
                  </div>
                  {graphData.links.length === 0 && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      No cross-institution match yet. Submit a fraud-ring application to see
                      an edge appear.
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                    {stats?.by_institution.map((i) => (
                      <span key={i.code}>
                        <span
                          className="mr-1.5 inline-block h-2 w-2 rounded-full"
                          style={{ background: CYAN }}
                        />
                        {i.display_name} — {i.signals_published} published
                      </span>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* ---- How it works ---- */}
          <Card
            className="aegis-enter"
            style={{ ...stagger(5), borderColor: "rgba(14,116,144,0.30)" }}
          >
            <CardHeader>
              <CardTitle>
                <TitleIcon icon={ShieldCheck} tone="brand" />
                How this works
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2.5">
                {HOW_IT_WORKS.map((line, i) => (
                  <li key={line} className="flex gap-2.5 text-[13px] leading-relaxed">
                    <span
                      className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{ background: "rgba(14,116,144,0.10)", color: CYAN }}
                    >
                      {i + 1}
                    </span>
                    <span className="text-muted-foreground">{line}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>

        {/* ---- Recent signals ---- */}
        <Card className="aegis-enter" style={stagger(6)}>
          <CardHeader>
            <CardTitle>
              <TitleIcon icon={Radio} tone="brand" />
              Recent network signals
            </CardTitle>
            <p className="aegis-section-desc mt-1">
              {signals?.privacy_note ??
                "Metadata only — digests are one-way and shown truncated."}
            </p>
          </CardHeader>
          <CardContent className="p-0">
            {!signals ? (
              <div className="space-y-2 px-5 pb-5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="aegis-label px-3 py-2">Published</th>
                      <th className="aegis-label px-3 py-2">Type</th>
                      <th className="aegis-label px-3 py-2">Reported by</th>
                      <th className="aegis-label px-3 py-2">Digest</th>
                      <th className="aegis-label px-3 py-2">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signals.signals.map((s, i) => (
                      <tr
                        key={`${s.hash_prefix}-${i}`}
                        className="border-b border-border/60 odd:bg-secondary/20"
                      >
                        <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
                          {formatTime(s.created_at)}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant="outline">{s.signal_type.replace("_", " ")}</Badge>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2">{s.reported_by}</td>
                        <td className="px-3 py-2 font-mono text-xs text-subtle">
                          {s.hash_prefix}…
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{s.notes ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
