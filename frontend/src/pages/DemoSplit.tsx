/**
 * Split-screen live demo: fraudster acts on the left, Aegis catches on the
 * right. Both panes are same-origin iframes and stay fully interactive.
 *
 * Responsive choice: BELOW 1024px the two panes become a tab toggle rather
 * than stacking vertically. Stacking would give each pane roughly half the
 * viewport height, and both panes are tall scrolling documents — a 400px-high
 * dashboard is useless. Tabs keep whichever pane you're looking at full-size,
 * and the iframes stay mounted (hidden, not unmounted) so switching tabs
 * never reloads the applicant form or loses in-progress state.
 *
 * The Fraud Bot Console floats over the LEFT pane only — it belongs to the
 * attacker's side of the story and is never rendered on standalone /apply.
 */

import { MonitorPlay } from "lucide-react";
import { useRef, useState } from "react";

import { FraudBotConsole } from "@/components/FraudBotConsole";

type Pane = "applicant" | "console";

export function DemoSplit() {
  const applyFrame = useRef<HTMLIFrameElement>(null);
  const [activePane, setActivePane] = useState<Pane>("applicant");

  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-center gap-2 border-b border-border bg-secondary/60 px-3 text-xs font-medium tracking-wide">
        <MonitorPlay className="h-3.5 w-3.5 shrink-0 text-amber-400" />
        <span className="font-semibold text-amber-400">AEGIS LIVE DEMO</span>
        <span className="hidden text-muted-foreground sm:inline">
          — Left: applicant view · Right: fraud operations console
        </span>

        {/* Pane switcher: only meaningful below the lg breakpoint. */}
        <div className="ml-auto flex items-center gap-1 lg:hidden">
          {(
            [
              ["applicant", "Applicant view"],
              ["console", "Fraud console"],
            ] as const
          ).map(([pane, label]) => (
            <button
              key={pane}
              onClick={() => setActivePane(pane)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                activePane === pane
                  ? "bg-amber-500/15 text-amber-300"
                  : "text-muted-foreground hover:bg-secondary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div
          className={`relative h-full w-full border-border lg:block lg:w-1/2 lg:border-r ${
            activePane === "applicant" ? "block" : "hidden"
          }`}
        >
          <iframe
            ref={applyFrame}
            src="/apply"
            title="Applicant view"
            className="h-full w-full bg-white"
          />
          <FraudBotConsole applyFrame={applyFrame} />
        </div>

        <div
          className={`h-full w-full lg:block lg:w-1/2 ${
            activePane === "console" ? "block" : "hidden"
          }`}
        >
          <iframe
            src="/dashboard?demo=1"
            title="Fraud operations console"
            className="h-full w-full"
          />
        </div>
      </div>
    </div>
  );
}
