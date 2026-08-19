/**
 * Fraud Bot Console — scripted attack simulation for the live demo.
 *
 * WHAT THIS IS: a deterministic script. It asks the backend for a
 * ready-made fraud profile, drives the applicant form via postMessage, and
 * submits through the exact same public API a real applicant uses.
 *
 * WHAT THIS IS NOT: an AI agent. There is no model, no reasoning, no
 * planning here — the attack patterns are fixed recipes. Aegis's genuine
 * LLM-based reasoning lives in the Investigation Agent on any flagged
 * application. Everything downstream of submission (OCR, scoring, ring
 * detection, explanation) is the real pipeline, unmocked.
 */

import { ChevronDown, ChevronUp, Terminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Tone = "info" | "warn" | "bad" | "good";
interface LogLine {
  t: string;
  text: string;
  tone: Tone;
}

const SCENARIOS = [
  { key: "bot_filler", label: "Run: Bot Session Attack" },
  { key: "identity_theft", label: "Run: Identity Theft Attack" },
  { key: "ring_operator", label: "Run: Fraud Ring Attack" },
] as const;

const TONE_CLASS: Record<Tone, string> = {
  info: "text-slate-300",
  warn: "text-amber-300",
  bad: "text-red-400",
  good: "text-emerald-400",
};

export function FraudBotConsole({ applyFrame }: { applyFrame: React.RefObject<HTMLIFrameElement> }) {
  const [open, setOpen] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [lines, setLines] = useState<LogLine[]>([]);
  const startedAt = useRef<number>(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const stamp = () => {
    const s = Math.max(0, Math.round((performance.now() - startedAt.current) / 1000));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };
  const log = (text: string, tone: Tone = "info") =>
    setLines((l) => [...l, { t: stamp(), text, tone }]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines]);

  /** Resolve the QL-XXXXXXXX reference to the real application row, then read its decision. */
  async function awaitDecision(reference: string) {
    const prefix = reference.replace(/^QL-/, "").toLowerCase();
    for (let attempt = 0; attempt < 8; attempt++) {
      try {
        const list = await api.listApplications({ limit: 15 });
        const match = list.items.find((i) => i.id.toLowerCase().startsWith(prefix));
        if (match) {
          const detail = await api.getApplication(match.id);
          if (detail.decision) return detail;
        }
      } catch {
        /* keep polling */
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    return null;
  }

  useEffect(() => {
    async function onMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const data = event.data ?? {};
      if (data.type !== "aegis:botProgress") return;

      if (data.stage === "filled") {
        log(`Auto-filled ${data.fields} fields in ${data.seconds}s`, "info");
      } else if (data.stage === "submitted") {
        log(`Application submitted — reference ${data.reference}`, "warn");
        log("Awaiting Aegis decision…", "info");
        const detail = await awaitDecision(data.reference);
        if (!detail?.decision) {
          log("No decision returned within 8s — check the console feed", "warn");
        } else {
          const band = detail.decision.decision_band;
          const score = detail.decision.calibrated_risk_score.toFixed(3);
          if (band === "AUTO_APPROVE") {
            log(`DECISION: AUTO_APPROVE @ ${score} — target passed undetected`, "good");
          } else {
            log(`DECISION: ${band} @ ${score} — target caught`, "bad");
          }
        }
        setRunning(null);
      } else if (data.stage === "error") {
        log(`Submission failed: ${data.message}`, "bad");
        setRunning(null);
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  async function runScenario(key: string) {
    setRunning(key);
    setLines([]);
    startedAt.current = performance.now();
    log("Target acquired: QuickLend loan application", "warn");
    try {
      const profile = await fetch(`${API}/demo/bot-profile?scenario=${key}`).then((r) => r.json());
      log(`Generating synthetic profile: ${profile.scenario_description}`, "info");
      const frame = applyFrame.current?.contentWindow;
      if (!frame) throw new Error("applicant view not ready");
      frame.postMessage(
        { type: "aegis:botFill", profile },
        window.location.origin
      );
      log("Driving applicant form…", "info");
    } catch (e) {
      log(`Attack aborted: ${(e as Error).message}`, "bad");
      setRunning(null);
    }
  }

  return (
    <div className="pointer-events-auto absolute bottom-3 left-3 z-30 w-[26rem] max-w-[calc(100%-1.5rem)] overflow-hidden rounded-lg border border-red-900/70 bg-[#0b0b0e] font-mono shadow-2xl">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 border-b border-red-900/60 bg-red-950/40 px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-bold tracking-wider text-red-400">
          <Terminal className="h-3.5 w-3.5" />
          ⚠ FRAUD BOT CONSOLE — scripted attack simulation
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-red-400/70" />
        ) : (
          <ChevronUp className="h-4 w-4 text-red-400/70" />
        )}
      </button>

      {open && (
        <div className="space-y-2.5 p-3">
          <p className="text-[10px] leading-relaxed text-slate-500">
            Deterministically generates realistic fraud patterns and submits them through the
            exact same public API real applicants use. Detection below is fully real — nothing
            is mocked.{" "}
            <span className="text-slate-400">
              This is not an AI agent (see the Investigation Agent on any flagged application
              for genuine LLM-based reasoning).
            </span>
          </p>

          <div className="grid gap-1.5">
            {SCENARIOS.map((s) => (
              <button
                key={s.key}
                onClick={() => runScenario(s.key)}
                disabled={running !== null}
                className="rounded border border-red-900/70 bg-red-950/30 px-2.5 py-1.5 text-left text-[11px] font-semibold text-red-300 transition-colors hover:bg-red-900/40 disabled:opacity-40"
              >
                {running === s.key ? `▸ running… ${s.label}` : s.label}
              </button>
            ))}
          </div>

          <div
            ref={scrollRef}
            className="h-40 overflow-y-auto rounded border border-slate-800 bg-black/60 p-2 text-[11px] leading-relaxed"
          >
            {lines.length === 0 ? (
              <p className="text-slate-600">$ awaiting attack selection…</p>
            ) : (
              lines.map((l, i) => (
                <p key={i} className={TONE_CLASS[l.tone]}>
                  <span className="text-slate-600">[{l.t}]</span> {l.text}
                </p>
              ))
            )}
          </div>

          {running === null && lines.length > 0 && (
            <button
              onClick={() => setLines([])}
              className="text-[10px] text-slate-500 hover:text-slate-300"
            >
              clear console · run again above
            </button>
          )}
        </div>
      )}
    </div>
  );
}
