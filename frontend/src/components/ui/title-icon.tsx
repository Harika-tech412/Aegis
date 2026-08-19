import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "amber" | "emerald" | "red" | "slate";

const TONE: Record<Tone, string> = {
  amber: "icon-chip-amber",
  emerald: "icon-chip-emerald",
  red: "icon-chip-red",
  slate: "icon-chip-slate",
};

/** Section/panel header icon in the system's translucent squircle. */
export function TitleIcon({
  icon: Icon,
  tone = "amber",
  className,
}: {
  icon: LucideIcon;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span className={cn("icon-chip", TONE[tone], className)}>
      <Icon className="h-4 w-4" />
    </span>
  );
}
