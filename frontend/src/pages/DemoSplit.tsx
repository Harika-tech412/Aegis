/**
 * Split-screen live demo: fraudster acts on the left, Aegis catches on the
 * right. Both panes are same-origin iframes and stay fully interactive.
 */

import { MonitorPlay } from "lucide-react";

export function DemoSplit() {
  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center justify-center gap-2 border-b border-border bg-secondary/60 px-4 text-xs font-medium tracking-wide">
        <MonitorPlay className="h-3.5 w-3.5 text-amber-400" />
        <span className="text-amber-400">AEGIS LIVE DEMO</span>
        <span className="text-muted-foreground">
          — Left: applicant view · Right: fraud operations console
        </span>
      </div>
      <div className="flex min-h-0 flex-1">
        <iframe
          src="/apply"
          title="Applicant view"
          className="h-full w-1/2 border-r border-border bg-white"
        />
        <iframe
          src="/dashboard?demo=1"
          title="Fraud operations console"
          className="h-full w-1/2"
        />
      </div>
    </div>
  );
}
