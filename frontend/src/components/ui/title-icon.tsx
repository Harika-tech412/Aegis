import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "brand" | "success" | "warning" | "danger" | "agent" | "neutral";

const TONE: Record<Tone, string> = {
  brand: "icon-chip-brand",
  success: "icon-chip-success",
  warning: "icon-chip-warning",
  danger: "icon-chip-danger",
  agent: "icon-chip-agent",
  neutral: "icon-chip-neutral",
};

/** Section/panel header icon in the system's translucent squircle. */
export function TitleIcon({
  icon: Icon,
  tone = "brand",
  className,
}: {
  icon: LucideIcon;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span className={cn("icon-chip", TONE[tone], className)}>
      <Icon className="h-4 w-4" strokeWidth={2} />
    </span>
  );
}
