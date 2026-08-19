import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export interface Stats {
  total: number;
  approve: number;
  review: number;
  flag: number;
}

const CARDS: { key: keyof Stats; label: string; accent: string }[] = [
  { key: "total", label: "Total applications", accent: "text-foreground" },
  { key: "approve", label: "Auto-approved", accent: "text-emerald-400" },
  { key: "review", label: "Human review", accent: "text-amber-400" },
  { key: "flag", label: "Auto-flagged", accent: "text-red-400" },
];

export function StatCards({ stats }: { stats: Stats | null }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {CARDS.map(({ key, label, accent }) => (
        <Card key={key}>
          <CardContent className="p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            {stats ? (
              <p className={`mt-1.5 text-3xl font-semibold tabular-nums ${accent}`}>
                {stats[key].toLocaleString()}
              </p>
            ) : (
              <Skeleton className="mt-2 h-8 w-20" />
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
