import { AlertOctagon, CheckCircle2, Inbox, UserSearch } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCountUp, stagger } from "@/lib/motion";

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
  chip: string;
  icon: typeof Inbox;
}[] = [
  { key: "total", label: "Total applications", accent: "text-foreground", chip: "icon-chip-brand", icon: Inbox },
  { key: "approve", label: "Auto-approved", accent: "text-success", chip: "icon-chip-success", icon: CheckCircle2 },
  { key: "review", label: "Human review", accent: "text-warning", chip: "icon-chip-warning", icon: UserSearch },
  { key: "flag", label: "Auto-flagged", accent: "text-danger", chip: "icon-chip-danger", icon: AlertOctagon },
];

function StatCard({
  index,
  label,
  accent,
  chip,
  icon: Icon,
  value,
  delta,
  compact = false,
}: {
  index: number;
  label: string;
  accent: string;
  chip: string;
  icon: typeof Inbox;
  value: number | null;
  delta: number;
  compact?: boolean;
}) {
  const shown = useCountUp(value);

  return (
    <Card className="aegis-enter aegis-surface-hover" style={stagger(index)}>
      <CardContent className={compact ? "p-3" : "p-4 sm:p-5"}>
        <div className="flex items-start justify-between gap-2">
          <p className="aegis-label leading-tight">{label}</p>
          <span className={`icon-chip ${chip}`}>
            <Icon className="h-4 w-4" />
          </span>
        </div>
        {value !== null ? (
          <>
            <p
              className={`aegis-metric ${accent} ${
                compact ? "mt-1 !text-2xl" : "mt-2"
              }`}
            >
              {shown.toLocaleString()}
            </p>
            <p className="mt-1 text-xs tabular-nums text-muted-foreground">
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
}

/**
 * `compact` is for the /demo split-screen, whose right pane is roughly half the
 * viewport — about 548px on a 1097px-wide screen. That is BELOW Tailwind's `sm`
 * breakpoint (640px), so the default responsive rules put all four cards in a
 * single column and consume ~380px of vertical space before the live feed even
 * starts. Compact mode fixes two columns regardless of width, because the pane
 * width is a property of the layout, not of the viewport.
 */
export function StatCards({
  stats,
  compact = false,
}: {
  stats: Stats | null;
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact
          ? "grid grid-cols-2 gap-2"
          : "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
      }
    >
      {CARDS.map((card, i) => (
        <StatCard
          key={card.key}
          index={i}
          label={card.label}
          accent={card.accent}
          chip={card.chip}
          icon={card.icon}
          value={stats ? stats[card.key] : null}
          delta={stats ? stats[card.key] - BASELINE_7D[card.key] : 0}
          compact={compact}
        />
      ))}
    </div>
  );
}
