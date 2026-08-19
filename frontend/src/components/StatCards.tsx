import { AlertOctagon, CheckCircle2, Inbox, UserSearch } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export interface Stats {
  total: number;
  approve: number;
  review: number;
  flag: number;
}

// The "vs 7d avg" baselines are static representative values for demo context
// only (a real deployment would compute a rolling window server-side). They
// are proportioned to the seeded band distribution so the deltas read sanely.
const BASELINE_7D: Stats = { total: 1150, approve: 566, review: 500, flag: 84 };

const CARDS: {
  key: keyof Stats;
  label: string;
  accent: string;
  icon: typeof Inbox;
}[] = [
  { key: "total", label: "Total applications", accent: "text-foreground", icon: Inbox },
  { key: "approve", label: "Auto-approved", accent: "text-emerald-400", icon: CheckCircle2 },
  { key: "review", label: "Human review", accent: "text-amber-400", icon: UserSearch },
  { key: "flag", label: "Auto-flagged", accent: "text-red-400", icon: AlertOctagon },
];

export function StatCards({ stats }: { stats: Stats | null }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {CARDS.map(({ key, label, accent, icon: Icon }) => {
        const delta = stats ? stats[key] - BASELINE_7D[key] : 0;
        return (
          <Card key={key}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {label}
                </p>
                <Icon className={`h-4 w-4 opacity-60 ${accent}`} />
              </div>
              {stats ? (
                <>
                  <p className={`mt-1 text-2xl font-semibold tabular-nums ${accent}`}>
                    {stats[key].toLocaleString()}
                  </p>
                  <p className="mt-0.5 text-xs tabular-nums text-muted-foreground">
                    {delta >= 0 ? "+" : ""}
                    {delta.toLocaleString()} vs 7d avg
                  </p>
                </>
              ) : (
                <Skeleton className="mt-2 h-8 w-20" />
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
