import { useCallback, useEffect, useState } from "react";

import { DriftWidget } from "@/components/DriftWidget";
import { LiveFeed } from "@/components/LiveFeed";
import { Navbar } from "@/components/Navbar";
import { ScoreDialog } from "@/components/ScoreDialog";
import { StatCards, type Stats } from "@/components/StatCards";
import { api } from "@/lib/api";

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

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
    } catch {
      /* stat cards keep their skeletons; the feed shows the real error */
    }
  }, []);

  useEffect(() => {
    loadStats();
    const timer = setInterval(loadStats, 10_000);
    return () => clearInterval(timer);
  }, [loadStats]);

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-7xl space-y-5 px-6 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Fraud operations</h1>
            <p className="text-sm text-muted-foreground">
              Live scoring across the application pipeline
            </p>
          </div>
          <ScoreDialog onScored={loadStats} />
        </div>

        <StatCards stats={stats} />

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <LiveFeed />
          </div>
          <div className="space-y-5">
            <DriftWidget />
          </div>
        </div>
      </main>
    </div>
  );
}
