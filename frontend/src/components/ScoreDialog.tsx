import { FileSearch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { ScoreRequest } from "@/lib/types";

const EMPLOYMENT_TYPES = ["salaried", "self_employed", "gig_worker", "unemployed"];
const LOAN_PURPOSES = [
  "debt_consolidation",
  "home_improvement",
  "medical",
  "education",
  "business",
  "other",
];

interface FormState extends ScoreRequest {}

const LEGIT_PRESET: FormState = {
  applicant_age: 38,
  annual_income: 68000,
  employment_type: "salaried",
  employer_name: "Sanchez PLC",
  requested_amount: 12000,
  loan_purpose: "home_improvement",
  loan_purpose_text: "Replacing the roof before the winter rains get in.",
  device_id: `demo_device_${Math.random().toString(36).slice(2, 8)}`,
  ip_hash: `demo_ip_${Math.random().toString(36).slice(2, 8)}`,
  session_duration_seconds: 230,
  mouse_movement_events: 170,
  form_paste_count: 1,
  applications_from_device_last_24h: 1,
  applications_from_ip_last_24h: 1,
  income_employer_consistency_score: 0.88,
  identity_consistency_score: 0.9,
};

const FRAUD_PRESET: Partial<FormState> = {
  annual_income: 175000,
  employment_type: "gig_worker",
  requested_amount: 48000,
  loan_purpose: "business",
  loan_purpose_text: "Personal use of funds.",
  session_duration_seconds: 22,
  mouse_movement_events: 2,
  form_paste_count: 9,
  applications_from_device_last_24h: 7,
  applications_from_ip_last_24h: 8,
  income_employer_consistency_score: 0.08,
  identity_consistency_score: 0.12,
};

function SliderField({
  label,
  hint,
  value,
  min,
  max,
  step = 1,
  onChange,
  format = (v: number) => String(v),
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <Label>{label}</Label>
        <span className="text-sm tabular-nums text-amber-300">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-secondary accent-amber-400"
      />
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

export function ScoreDialog({ onScored }: { onScored?: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<FormState>({ ...LEGIT_PRESET });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const freshIds = () => ({
    device_id: `demo_device_${Math.random().toString(36).slice(2, 8)}`,
    ip_hash: `demo_ip_${Math.random().toString(36).slice(2, 8)}`,
  });

  async function submit() {
    setBusy(true);
    try {
      const result = await api.score(form);
      const band = result.decision.decision_band.replace("_", "-");
      toast.success(`Scored: ${band}`, {
        description: `Calibrated risk ${result.decision.calibrated_risk_score.toFixed(3)} in ${result.decision.latency_ms.toFixed(0)}ms — watch the live feed.`,
      });
      setOpen(false);
      onScored?.();
    } catch (e) {
      toast.error("Scoring failed", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Quick manual test (advanced, no ID upload)
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Quick manual test</DialogTitle>
          <DialogDescription>
            Test the tabular and behavioral signals directly against the live scoring engine.
            Use a preset, then adjust the sliders to see the decision change.
          </DialogDescription>
        </DialogHeader>

        <div className="mb-4 flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setForm({ ...LEGIT_PRESET, ...freshIds() })}
          >
            Preset: typical legitimate
          </Button>
          <Button
            variant="secondary"
            size="sm"
            className="border-red-900 text-red-300"
            onClick={() => setForm((f) => ({ ...f, ...FRAUD_PRESET, ...freshIds() }))}
          >
            Preset: obvious fraud
          </Button>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>Applicant age</Label>
            <Input
              type="number"
              min={18}
              max={100}
              value={form.applicant_age}
              onChange={(e) => set("applicant_age", Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <Label>Declared annual income ($)</Label>
            <Input
              type="number"
              min={0}
              value={form.annual_income}
              onChange={(e) => set("annual_income", Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <Label>Employment type</Label>
            <select
              value={form.employment_type}
              onChange={(e) => set("employment_type", e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
            >
              {EMPLOYMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Requested amount ($)</Label>
            <Input
              type="number"
              min={1000}
              max={50000}
              value={form.requested_amount}
              onChange={(e) => set("requested_amount", Number(e.target.value))}
            />
          </div>
          <div className="space-y-1">
            <Label>Loan purpose</Label>
            <select
              value={form.loan_purpose}
              onChange={(e) => set("loan_purpose", e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
            >
              {LOAN_PURPOSES.map((p) => (
                <option key={p} value={p}>
                  {p.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Stated reason (free text)</Label>
            <Input
              value={form.loan_purpose_text}
              onChange={(e) => set("loan_purpose_text", e.target.value)}
            />
          </div>

          <div className="sm:col-span-2 mt-1 border-t border-border pt-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Behavioral & network signals
            </p>
            <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
              <SliderField
                label="Applications from this device (24h)"
                hint="How many applications this device fingerprint submitted today"
                value={form.applications_from_device_last_24h ?? 1}
                min={1}
                max={10}
                onChange={(v) => set("applications_from_device_last_24h", v)}
              />
              <SliderField
                label="Applications from this IP (24h)"
                hint="How many applications came from this network address today"
                value={form.applications_from_ip_last_24h ?? 1}
                min={1}
                max={10}
                onChange={(v) => set("applications_from_ip_last_24h", v)}
              />
              <SliderField
                label="Mouse movement events"
                hint="Near zero suggests a bot or scripted session"
                value={form.mouse_movement_events}
                min={0}
                max={300}
                onChange={(v) => set("mouse_movement_events", v)}
              />
              <SliderField
                label="Pasted form fields"
                hint="Humans type; scripts paste every field"
                value={form.form_paste_count}
                min={0}
                max={12}
                onChange={(v) => set("form_paste_count", v)}
              />
              <SliderField
                label="Session duration (seconds)"
                hint="How long the applicant spent on the form"
                value={form.session_duration_seconds}
                min={10}
                max={600}
                onChange={(v) => set("session_duration_seconds", v)}
              />
              <SliderField
                label="Income–employer consistency"
                hint="From verification: does the income fit the employer? (low = suspicious)"
                value={form.income_employer_consistency_score}
                min={0}
                max={1}
                step={0.01}
                format={(v) => v.toFixed(2)}
                onChange={(v) => set("income_employer_consistency_score", v)}
              />
              <SliderField
                label="Identity consistency"
                hint="From verification: do name/address/phone records agree? (low = suspicious)"
                value={form.identity_consistency_score}
                min={0}
                max={1}
                step={0.01}
                format={(v) => v.toFixed(2)}
                onChange={(v) => set("identity_consistency_score", v)}
              />
            </div>
          </div>
        </div>

        {/* ID document verification deliberately lives ONLY in the Live Demo,
            where it runs real OCR + perceptual-hash reuse detection. This
            dialog is a tabular-signals test bench and never asks anyone to
            transcribe a document by hand. */}
        <div className="mt-5 flex items-start gap-2.5 rounded-md border border-border bg-secondary/30 p-3 text-sm text-muted-foreground">
          <FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <span>
            For full ID document verification with OCR, use the{" "}
            <Link to="/demo" className="font-medium text-amber-400 hover:underline">
              Live Demo
            </Link>
            .
          </span>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? "Scoring…" : "Submit for scoring"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
