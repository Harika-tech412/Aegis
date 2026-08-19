import { ArrowRight, MonitorPlay } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { LiveFeed } from "@/components/LiveFeed";
import { ModelHealthCard } from "@/components/ModelHealthCard";
import { Navbar } from "@/components/Navbar";
import { ScoreDialog } from "@/components/ScoreDialog";
import { StatCards, type Stats } from "@/components/StatCards";
import { api } from "@/lib/api";
import { stagger } from "@/lib/motion";

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [lastSynced, setLastSynced] = useState<Date | null>(null);
  // Inside the split-screen demo (?demo=1) the feed polls faster so a
  // submission on the applicant side lands within ~2 seconds.
  const [searchParams] = useSearchParams();
  const demoMode = searchParams.get("demo") === "1";

  // Band counts come from the list endpoint's filtered totals (limit=1 keeps
  // the payloads tiny) — no dedicated stats endpoint needed at this scale.
  const loadStats = useCallback(async () => {
    try {
      const [all, approve, review, flag] = await Promise.all([
        api.listApplications({ limit: 1 }),
        api.listApplications({ limit: 1, decision_band: "AUTO_APPROVE" }),
        api.listApplications({ limit: 1, decision_band: "HUMAN_REVIEW" }),
        api.listApplications({ limit: 1, decision_band: "AUTO_FLAG" }),
      ]);
      setStats({
        total: all.total,
        approve: approve.total,
        review: review.total,
        flag: flag.total,
      });
      setLastSynced(new Date());
    } catch {
      /* stat cards keep their skeletons; the feed shows the real error */
    }
  }, []);

  useEffect(() => {
    loadStats();
    const timer = setInterval(loadStats, 10_000);
    return () => clearInterval(timer);
  }, [loadStats]);

  const today = new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 space-y-4 px-4 py-5 sm:px-6">
        {/* Primary CTA. Hidden inside the split-screen demo itself (?demo=1),
            where this dashboard IS the right-hand pane. */}
        {!demoMode && (
          <Link
            to="/demo"
            className="aegis-enter aegis-surface-hover flex flex-wrap items-center justify-between gap-4 rounded-xl border border-brand/50 bg-brand/10 px-5 py-4"
          >
            <div className="flex items-center gap-4">
              <span className="icon-chip icon-chip-brand !p-2.5">
                <MonitorPlay className="h-6 w-6" />
              </span>
              <div>
                <p className="text-base font-semibold tracking-tight text-brand sm:text-lg">
                  Open Live Demo (Applicant + Fraud Console)
                </p>
                <p className="mt-0.5 text-sm leading-relaxed text-brand/70">
                  Split-screen: submit an application as a fraudster on the left, watch Aegis
                  catch it on the right — with real OCR ID verification.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-brand-foreground">
              Launch <ArrowRight className="h-4 w-4" />
            </span>
          </Link>
        )}

        <div className="aegis-enter flex flex-wrap items-end justify-between gap-3" style={stagger(1)}>
          <div>
            <p className="aegis-overline">Overview · {today}</p>
            <h1 className="aegis-title mt-1">Fraud operations</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Live scoring across the application pipeline
            </p>
          </div>
          <ScoreDialog onScored={loadStats} />
        </div>

        <StatCards stats={stats} />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="aegis-enter xl:col-span-2" style={stagger(6)}>
            <LiveFeed pollMs={demoMode ? 2000 : 3500} />
          </div>
          <div className="aegis-enter space-y-4" style={stagger(7)}>
            <ModelHealthCard />
          </div>
        </div>
      </main>

      {/* Calm status footer — deliberately quiet, never competes for attention. */}
      <footer className="border-t border-border bg-background/80">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[11px] text-muted-foreground sm:px-6">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            All systems operational
          </span>
          <span className="text-border">·</span>
          <span>
            Last synced{" "}
            {lastSynced
              ? lastSynced.toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })
              : "—"}
          </span>
          <span className="text-border">·</span>
          <span>Demo environment · synthetic data</span>
        </div>
      </footer>
    </div>
  );
}
