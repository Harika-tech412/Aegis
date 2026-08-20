/**
 * Applicant Notice — a plain-language letter, not a system output.
 *
 * Deliberately the least product-like of the three views: light, roomy,
 * comfortable reading width, no charts, no risk score, no jargon. The reasons
 * arrive already softened by the endpoint; this view adds no technical detail
 * of its own.
 *
 * Style isolation: explicit Tailwind utilities only (bg-white / text-slate-*),
 * no design-system token overrides, so the dark theme elsewhere is unaffected.
 */

import { Printer } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import type { ApplicantReport } from "@/lib/types";

import "./reports.css";

export function ApplicantView({
  report,
  loading,
  error,
}: {
  report: ApplicantReport | null;
  loading: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <p className="text-sm text-danger">Could not generate the applicant notice — {error}</p>
      </div>
    );
  }
  if (loading || !report) {
    return (
      <div className="space-y-3 rounded-xl border border-border bg-card p-6">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const decisionDate = new Date(report.decision_date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="report-document mx-auto w-full max-w-[680px] rounded-2xl bg-white px-7 py-9 text-slate-800 shadow-sm sm:px-10 sm:py-11">
      <div className="report-section flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-slate-900">
            About your recent application
          </h1>
          <p className="mt-1.5 text-sm text-slate-500">{decisionDate}</p>
        </div>
        <button
          onClick={() => window.print()}
          className="report-noprint inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
        >
          <Printer className="h-3.5 w-3.5" strokeWidth={2} />
          Print
        </button>
      </div>

      {/* ---- Opening ---- */}
      <div className="report-section mt-7 space-y-4 text-[15px] leading-[1.75]">
        <p>Dear applicant,</p>
        <p>
          Thank you for applying with us. We have finished reviewing your application, and we
          want to explain the outcome clearly and tell you what you can do next.
        </p>
        <p className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 font-medium text-slate-900">
          {report.decision_outcome}
        </p>
      </div>

      {/* ---- Why ---- */}
      {report.primary_reasons.length > 0 && (
        <section className="report-section mt-8">
          <h2 className="text-[17px] font-semibold text-slate-900">Why this happened</h2>
          <p className="mt-1.5 text-[14px] leading-relaxed text-slate-600">
            These are the main things that affected the outcome:
          </p>
          <ul className="mt-3.5 space-y-3">
            {report.primary_reasons.map((reason) => (
              <li key={reason} className="flex gap-3 text-[15px] leading-[1.7]">
                <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---- What you can do ---- */}
      <section className="report-section mt-8">
        <h2 className="text-[17px] font-semibold text-slate-900">What you can do next</h2>
        <ol className="mt-3.5 space-y-3.5">
          {report.what_you_can_do.map((step, i) => (
            <li key={step} className="flex gap-3.5 text-[15px] leading-[1.7]">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[12px] font-semibold text-slate-700">
                {i + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      {/* ---- Rights ---- */}
      <section className="report-section mt-8 rounded-xl border border-slate-200 bg-slate-50/70 px-5 py-5">
        <h2 className="text-[17px] font-semibold text-slate-900">Your rights</h2>
        <ul className="mt-3 space-y-2.5">
          {report.your_rights.map((right) => (
            <li key={right} className="flex gap-3 text-[14px] leading-[1.7] text-slate-700">
              <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-slate-400" />
              <span>{right}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* ---- Footer ---- */}
      <footer className="report-section mt-8 border-t border-slate-200 pt-5 text-[14px] leading-[1.7] text-slate-600">
        <h2 className="text-[15px] font-semibold text-slate-900">How to contact us</h2>
        <p className="mt-1.5">{report.contact_note}</p>
        <p className="mt-4">
          <span className="text-slate-500">Your reference number:</span>{" "}
          <span className="font-mono text-[13px] font-semibold text-slate-900">
            {report.appeal_reference_code}
          </span>
        </p>
        <p className="mt-5 text-[11px] italic leading-relaxed text-slate-400">
          {report.data_disclosure}
        </p>
      </footer>
    </div>
  );
}
