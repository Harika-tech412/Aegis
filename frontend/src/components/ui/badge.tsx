import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Compact enterprise badge. Status meaning is carried by label text too, never colour alone. */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-border-emphasis bg-secondary text-muted-foreground",
        brand: "border-brand/40 bg-brand/10 text-brand",
        approve: "border-success/40 bg-success/10 text-success",
        review: "border-warning/40 bg-warning/10 text-warning",
        flag: "border-danger/40 bg-danger/10 text-danger",
        agent: "border-agent/40 bg-agent/10 text-agent",
        outline: "border-border text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
