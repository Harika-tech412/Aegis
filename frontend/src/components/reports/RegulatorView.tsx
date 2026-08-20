/**
 * Regulator View — a formal compliance document, not a dashboard panel.
 *
 * Deliberately inverted from the app's dark theme: black-on-off-white, dense,
 * printable. The inversion is the point — it signals "this is a document you
 * would hand to an examiner", not another product surface.
 *
 * Style isolation: every colour here is an explicit Tailwind utility
 * (bg-white / text-slate-900 / border-slate-300). No design-system token is
 * overridden, so nothing leaks into the dark theme elsewhere in the app.
 */

import { Printer } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import type { RegulatorReport } from "@/lib/types";

import "./reports.css";

const GOVERNANCE_LABELS: Record<string, string> = {
  training_data: "Training data",
  holdout_performance: "Holdout performance",
  calibration_status: "Calibration status",
  drift_monitoring: "Drift monitoring methodology",
  explainability_method: "Explainability method",
  known_limitations: "Known limitations",
};

function Section({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="report-section border-t border-slate-300 pt-5">
      <h2 className="mb-3 text-[13px] font-bold uppercase tracking-[0.1em] text-slate-900">
        <span className="mr-2 text-slate-500">{number}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

export function RegulatorView({
  report,
  loading,
  error,
}: {
  report: RegulatorReport | null;
  loading: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-sm text-danger">Could not generate the regulatory report — {error}</p>
      </div>
    );
  }
  if (loading || !report) {
    return (
      <div className="space-y-3 rounded-xl border border-border bg-card p-6">
        <Skeleton className="h-6 w-72" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const s = report.decision_summary;

  return (
    <div className="report-document mx-auto max-w-4xl bg-[#FAFAF8] px-8 py-8 text-slate-900 shadow-sm sm:px-12 sm:py-10">
      {/* ---- Masthead ---- */}
      <header className="report-section mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold uppercase tracking-[0.08em] text-slate-900">
              Regulatory Decision Report
            </h1>
            <p className="mt-1.5 text-xs font-medium text-slate-600">
              Application reference{" "}
              <span className="font-mono font-semibold text-slate-900">
                {s.application_id}
              </span>
            </p>
            <p className="text-xs text-slate-600">
              Report generated {new Date(report.report_generated_at).toUTCString()} · version{" "}
              {report.report_version}
            </p>
          </div>
          <button
            onClick={() => window.print()}
            className="report-noprint inline-flex items-center gap-2 rounded-lg border border-slate-400 bg-white px-3 py-2 text-xs font-semibold text-slate-800 transition-colors hover:bg-slate-100"
          >
            <Printer className="h-3.5 w-3.5" strokeWidth={2} />
            Print / Export PDF
          </button>
        </div>
      </header>

      <div className="space-y-6">
        {/* ---- 1. Decision summary ---- */}
        <Section number="1." title="Decision Summary">
          <table className="w-full text-[13px] leading-relaxed">
            <tbody>
              {[
                ["Application identifier", s.application_id],
                ["Application received", new Date(s.timestamp).toUTCString()],
                ["Decision band assigned", s.decision_band],
                ["Calibrated risk score", s.calibrated_risk_score.toFixed(6)],
                ["Model version", s.model_version],
                ["Scoring latency", `${s.scoring_latency_ms} ms`],
              ].map(([label, value]) => (
                <tr key={label} className="border-b border-slate-200 last:border-0">
                  <td className="w-1/3 py-1.5 pr-4 align-top font-medium text-slate-600">
                    {label}
                  </td>
                  <td className="py-1.5 font-semibold text-slate-900">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        {/* ---- 2. Fair lending disclosure — the compliance headline ---- */}
        <Section number="2." title="Fair Lending Disclosure">
          <div className="rounded-lg border-2 border-slate-800 bg-white p-4">
            <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-slate-700">
              Prohibited bases excluded from model inputs
            </p>
            <ul className="mt-2.5 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
              {report.fair_lending_disclosure.prohibited_bases_excluded.map((basis) => (
                <li key={basis} className="flex items-baseline gap-2 text-[13px] text-slate-900">
                  <span className="font-bold text-slate-900">&times;</span>
                  <span className="font-medium">{basis.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3.5 border-t border-slate-300 pt-3 text-[12.5px] font-medium leading-relaxed text-slate-800">
              {report.fair_lending_disclosure.attestation}
            </p>
            <p className="mt-2 text-[11px] text-slate-600">
              Feature specification of record:{" "}
              <span className="font-mono">
                {report.fair_lending_disclosure.feature_specification_reference}
              </span>
            </p>
          </div>
        </Section>

        {/* ---- 3. Decision provenance ---- */}
        <Section number="3." title="Decision Provenance">
          <p className="mb-3 text-[12.5px] leading-relaxed text-slate-700">
            Every computational step that produced this decision, in order of execution.
          </p>
          <ol className="space-y-2.5">
            {report.decision_provenance.map((step) => (
              <li key={step.step} className="flex gap-3 text-[13px] leading-relaxed">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-400 bg-white text-[11px] font-bold text-slate-800">
                  {step.step}
                </span>
                <div>
                  <p className="font-semibold text-slate-900">{step.stage}</p>
                  <p className="text-slate-700">{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>

        {/* ---- 4. Contributing factors — tabular, not a chart ---- */}
        <Section number="4." title="Contributing Factors">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="border-y border-slate-400 bg-slate-100 text-left">
                <th className="px-2 py-2 font-bold uppercase tracking-wider text-slate-700">
                  Factor
                </th>
                <th className="px-2 py-2 font-bold uppercase tracking-wider text-slate-700">
                  Direction
                </th>
                <th className="px-2 py-2 font-bold uppercase tracking-wider text-slate-700">
                  Basis
                </th>
                <th className="px-2 py-2 font-bold uppercase tracking-wider text-slate-700">
                  Description
                </th>
              </tr>
            </thead>
            <tbody>
              {report.top_contributing_factors.map((f) => (
                <tr key={f.factor} className="border-b border-slate-200 align-top">
                  <td className="px-2 py-2 font-mono text-[11.5px] font-medium text-slate-900">
                    {f.factor}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 font-semibold text-slate-800">
                    {f.direction}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-slate-700">{f.basis}</td>
                  <td className="px-2 py-2 leading-relaxed text-slate-700">{f.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        {/* ---- 5. Model governance ---- */}
        <Section number="5." title="Model Governance &amp; Validation">
          <dl className="space-y-2.5 text-[13px] leading-relaxed">
            {Object.entries(report.model_governance).map(([key, value]) => (
              <div key={key}>
                <dt className="font-semibold text-slate-900">
                  {GOVERNANCE_LABELS[key] ?? key.replace(/_/g, " ")}
                </dt>
                <dd className="text-slate-700">{value}</dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ---- 6. Human review ---- */}
        <Section number="6." title="Human Review Status">
          <p className="text-[13px] font-semibold text-slate-900">
            {report.human_review_status.status}
          </p>
          {report.human_review_status.reviewed && (
            <table className="mt-2.5 w-full text-[13px]">
              <tbody>
                {[
                  ["Verdict", report.human_review_status.verdict?.replace(/_/g, " ")],
                  ["Reviewer", report.human_review_status.reviewer],
                  [
                    "Reviewed at",
                    report.human_review_status.reviewed_at
                      ? new Date(report.human_review_status.reviewed_at).toUTCString()
                      : null,
                  ],
                  ["Notes", report.human_review_status.notes || "None recorded"],
                ].map(([label, value]) => (
                  <tr key={String(label)} className="border-b border-slate-200 last:border-0">
                    <td className="w-1/3 py-1.5 pr-4 align-top font-medium text-slate-600">
                      {label}
                    </td>
                    <td className="py-1.5 text-slate-900">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>

        {/* ---- 7. Audit trail ---- */}
        <Section number="7." title="Audit Trail">
          <p className="text-[13px] leading-relaxed text-slate-700">
            <span className="font-semibold text-slate-900">
              {report.audit_trail_reference.audit_log_entry_count}
            </span>{" "}
            audit log {report.audit_trail_reference.audit_log_entry_count === 1 ? "entry" : "entries"}{" "}
            recorded against application reference{" "}
            <span className="font-mono font-semibold text-slate-900">
              {report.audit_trail_reference.application_id}
            </span>
            . {report.audit_trail_reference.cross_reference_note}
          </p>
        </Section>
      </div>

      {/* ---- Footer ---- */}
      <footer className="report-section mt-8 border-t-2 border-slate-800 pt-4">
        <p className="text-[11.5px] leading-relaxed text-slate-700">
          Report generated {new Date(report.report_generated_at).toUTCString()}. This report is
          generated automatically from the Aegis decision record. All data derives from the audit
          trail.
        </p>
        <p className="mt-1.5 text-[10.5px] italic text-slate-500">
          {report.data_disclosure}
        </p>
      </footer>
    </div>
  );
}
