/**
 * Split-screen live demo: fraudster acts on the left, Aegis catches on the
 * right. Both panes are same-origin iframes and stay fully interactive.
 *
 * The Fraud Bot Console floats over the LEFT pane only — it belongs to the
 * attacker's side of the story and is deliberately never rendered on the
 * standalone /apply route.
 */

import { MonitorPlay } from "lucide-react";
import { useRef } from "react";

import { FraudBotConsole } from "@/components/FraudBotConsole";

export function DemoSplit() {
  const applyFrame = useRef<HTMLIFrameElement>(null);

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
        <div className="relative h-full w-1/2 border-r border-border">
          <iframe
            ref={applyFrame}
            src="/apply"
            title="Applicant view"
            className="h-full w-full bg-white"
          />
          <FraudBotConsole applyFrame={applyFrame} />
        </div>
        <iframe
          src="/dashboard?demo=1"
          title="Fraud operations console"
          className="h-full w-1/2"
        />
      </div>
    </div>
  );
}
