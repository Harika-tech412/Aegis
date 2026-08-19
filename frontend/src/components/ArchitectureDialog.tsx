import { Network } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const DIFFERENTIATORS = [
  "6 signal modalities fused: tabular, behavioral, velocity, free-text, document, graph",
  "Real-time scoring under 200ms, calibrated so scores read as true probabilities",
  "Explainable by construction: SHAP attributions plus counterfactual 'what would change this'",
  "Graph-based fraud-ring detection over shared device / IP fingerprints",
  "Human-in-the-loop: investigator verdicts feed a demonstrated retraining pipeline",
  "Model drift monitoring via PSI — the metric banking model-risk teams actually use",
];

/** One box in the pipeline SVG. */
function Box({ x, y, w, h, title, sub, accent = false }: {
  x: number; y: number; w: number; h: number; title: string; sub?: string; accent?: boolean;
}) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={6}
        fill={accent ? "#121D30" : "#0D1626"} stroke={accent ? "#3B82F6" : "#223047"} strokeWidth={1} />
      <text x={x + w / 2} y={y + (sub ? h / 2 - 4 : h / 2 + 4)} textAnchor="middle"
        fill="#F1F5F9" fontSize="11" fontWeight="600">{title}</text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 12} textAnchor="middle" fill="#94A3B8" fontSize="9">
          {sub}
        </text>
      )}
    </g>
  );
}

function Arrow({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  return (
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#2C3E58" strokeWidth={1.5}
      markerEnd="url(#arrowhead)" />
  );
}

export function ArchitectureDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <Network className="h-4 w-4" /> Architecture
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Aegis pipeline</DialogTitle>
          <DialogDescription>
            From raw application to investigator decision, end to end.
          </DialogDescription>
        </DialogHeader>

        <div className="overflow-x-auto rounded-md border border-border bg-background/60 p-3">
          <svg viewBox="0 0 740 330" className="min-w-[680px]" role="img"
            aria-label="Aegis pipeline diagram">
            <defs>
              <marker id="arrowhead" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                <polygon points="0 0, 7 3.5, 0 7" fill="#2C3E58" />
              </marker>
            </defs>

            {/* Row 1: intake -> features -> models */}
            <Box x={10} y={20} w={130} h={44} title="Application intake" sub="+ optional ID document" />
            <Arrow x1={140} y1={42} x2={168} y2={42} />
            <Box x={170} y={20} w={130} h={44} title="Feature engineering" sub="shared train/serve code" />
            <Arrow x1={300} y1={42} x2={328} y2={42} />
            <Box x={330} y={8} w={128} h={32} title="XGBoost" sub="" />
            <Box x={330} y={46} w={128} h={32} title="Isolation Forest" sub="" />
            <Arrow x1={458} y1={24} x2={486} y2={38} />
            <Arrow x1={458} y1={62} x2={486} y2={48} />
            <Box x={488} y={20} w={116} h={44} title="Ensemble" sub="isotonic calibration" />
            <Arrow x1={604} y1={42} x2={632} y2={42} />
            <Box x={634} y={20} w={96} h={44} title="Decision bands" sub="approve / review / flag" accent />

            {/* Row 2: intelligence layers fanning out of the decision */}
            <Arrow x1={682} y1={64} x2={682} y2={98} />
            <line x1={92} y1={120} x2={682} y2={120} stroke="#2C3E58" strokeWidth={1} strokeDasharray="3 3" />
            <line x1={92} y1={120} x2={92} y2={138} stroke="#2C3E58" strokeWidth={1} />
            <line x1={260} y1={120} x2={260} y2={138} stroke="#2C3E58" strokeWidth={1} />
            <line x1={430} y1={120} x2={430} y2={138} stroke="#2C3E58" strokeWidth={1} />
            <line x1={600} y1={120} x2={600} y2={138} stroke="#2C3E58" strokeWidth={1} />
            <line x1={682} y1={98} x2={682} y2={120} stroke="#2C3E58" strokeWidth={1} />

            <Box x={22} y={140} w={140} h={44} title="SHAP → LLM explanation" sub="template fallback, never down" />
            <Box x={190} y={140} w={140} h={44} title="Fraud ring detection" sub="device / IP graph" />
            <Box x={360} y={140} w={140} h={44} title="Similar past cases" sub="RAG via pgvector" />
            <Box x={530} y={140} w={140} h={44} title="Counterfactuals" sub="what would change this" />

            {/* Row 3: investigator + feedback loop */}
            <Arrow x1={92} y1={184} x2={200} y2={228} />
            <Arrow x1={260} y1={184} x2={280} y2={226} />
            <Arrow x1={430} y1={184} x2={390} y2={226} />
            <Arrow x1={600} y1={184} x2={470} y2={230} />
            <Box x={200} y={230} w={280} h={46} title="Investigator dashboard" sub="human-in-the-loop review queue" accent />

            {/* Feedback loop back to the model */}
            <path d="M 480 253 C 640 253, 700 200, 700 120 C 700 90, 620 74, 605 60"
              fill="none" stroke="#8B5CF6" strokeWidth={1.4} strokeDasharray="5 4"
              markerEnd="url(#arrowhead)" />
            <text x={640} y={272} fill="#8B5CF6" fontSize="10">
              verdicts → retraining
            </text>

            {/* Drift monitor note */}
            <Box x={22} y={288} w={200} h={32} title="Drift monitor (PSI)" sub="" />
            <line x1={222} y1={304} x2={330} y2={304} stroke="#2C3E58" strokeWidth={1} strokeDasharray="3 3" />
            <text x={340} y={308} fill="#94A3B8" fontSize="10">
              watches live traffic vs training distribution
            </text>
          </svg>
        </div>

        <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {DIFFERENTIATORS.map((d) => (
            <li key={d} className="flex items-start gap-2 text-sm text-muted-foreground">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              {d}
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
