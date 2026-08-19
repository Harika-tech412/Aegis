import { AlertOctagon, CheckCircle2, UserSearch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { DecisionBand } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Status is carried by icon + text as well as colour (never colour alone). */
const CONFIG: Record<
  DecisionBand,
  { label: string; variant: "approve" | "review" | "flag"; icon: typeof CheckCircle2 }
> = {
  AUTO_APPROVE: { label: "Auto-approve", variant: "approve", icon: CheckCircle2 },
  HUMAN_REVIEW: { label: "Human review", variant: "review", icon: UserSearch },
  AUTO_FLAG: { label: "Auto-flag", variant: "flag", icon: AlertOctagon },
};

export function BandBadge({
  band,
  className,
}: {
  band: DecisionBand | null | undefined;
  className?: string;
}) {
  if (!band) return <Badge variant="outline" className={className}>—</Badge>;
  const { label, variant, icon: Icon } = CONFIG[band];
  return (
    <Badge variant={variant} className={cn(className)}>
      <Icon className="h-3 w-3" strokeWidth={2.5} />
      {label}
    </Badge>
  );
}
