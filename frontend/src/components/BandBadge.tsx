import { Badge } from "@/components/ui/badge";
import type { DecisionBand } from "@/lib/types";
import { cn } from "@/lib/utils";

const CONFIG: Record<DecisionBand, { label: string; variant: "approve" | "review" | "flag" }> = {
  AUTO_APPROVE: { label: "AUTO-APPROVE", variant: "approve" },
  HUMAN_REVIEW: { label: "HUMAN REVIEW", variant: "review" },
  AUTO_FLAG: { label: "AUTO-FLAG", variant: "flag" },
};

export function BandBadge({
  band,
  className,
}: {
  band: DecisionBand | null | undefined;
  className?: string;
}) {
  if (!band) return <Badge variant="outline" className={className}>—</Badge>;
  const { label, variant } = CONFIG[band];
  return (
    <Badge variant={variant} className={cn(className)}>
      {label}
    </Badge>
  );
}
