import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BandBadge } from "@/components/BandBadge";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { Navbar } from "@/components/Navbar";
import { RingPanel } from "@/components/RingPanel";
import { ShapChart } from "@/components/ShapChart";
import { SimilarCasesPanel } from "@/components/SimilarCasesPanel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  ApplicationDetail as AppDetail,
  RingInfo,
  SimilarCasesResponse,
} from "@/lib/types";
import { formatMoney, formatTime } from "@/lib/utils";

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();

  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [ring, setRing] = useState<RingInfo | null>(null);
  const [ringError, setRingError] = useState<string | null>(null);
  const [similar, setSimilar] = useState<SimilarCasesResponse | null>(null);
  const [similarError, setSimilarError] = useState<string | null>(null);

  // Three independent fetches — each panel loads (or fails) on its own; the
  // similar-cases search is the slowest and must never block the header.
  useEffect(() => {
    if (!id) return;
    setDetail(null);
    setRing(null);
    setSimilar(null);
    api.getApplication(id).then(setDetail).catch((e) => setDetailError(e.message));
    api.getRing(id).then(setRing).catch((e) => setRingError(e.message));
    api.getSimilarCases(id).then(setSimilar).catch((e) => setSimilarError(e.message));
  }, [id]);

  if (detailError) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <main className="mx-auto max-w-4xl px-6 py-16 text-center">
          <p className="text-sm text-red-400">Could not load this application — {detailError}</p>
          <Link to="/dashboard" className="mt-4 inline-block text-sm text-muted-foreground underline">
            Back to dashboard
          </Link>
        </main>
      </div>
    );
  }

  const decision = detail?.decision ?? null;

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="mx-auto max-w-5xl space-y-5 px-6 py-6">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Link>

        {/* ---- Header ---- */}
        {!detail ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Card>
            <CardContent className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <BandBadge band={decision?.decision_band} className="px-3 py-1 text-sm" />
                    {decision && (
                      <span className="text-2xl font-semibold tabular-nums">
                        {decision.calibrated_risk_score.toFixed(3)}
                        <span className="ml-1.5 text-sm font-normal text-muted-foreground">
                          calibrated risk
                        </span>
                      </span>
                    )}
                  </div>
                  <p className="mt-2 font-mono text-xs text-muted-foreground">{detail.id}</p>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <p>Received {formatTime(detail.created_at)}</p>
                  {decision && <p>Scored in {decision.latency_ms.toFixed(0)}ms · {decision.model_version}</p>}
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-x-8 gap-y-3 border-t border-border pt-4 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Income</p>
                  <p className="mt-0.5">{formatMoney(detail.annual_income)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Employment</p>
                  <p className="mt-0.5">
                    {detail.employment_type.replace("_", " ")} · {detail.employer_name}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Requested</p>
                  <p className="mt-0.5">{formatMoney(detail.requested_amount)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Purpose</p>
                  <p className="mt-0.5">{detail.loan_purpose.replace("_", " ")}</p>
                </div>
              </div>
              {detail.loan_purpose_text && (
                <p className="mt-3 rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm italic text-muted-foreground">
                  “{detail.loan_purpose_text}”
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* ---- Explanation + SHAP ---- */}
        {!detail ? (
          <Skeleton className="h-72 w-full" />
        ) : (
          decision && (
            <Card>
              <CardHeader>
                <CardTitle>Why the model decided this</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-5 rounded-md border border-border bg-secondary/40 p-4 text-sm leading-relaxed">
                  {decision.explanation_text}
                </p>
                {detail.top_shap_features.length > 0 && (
                  <ShapChart features={detail.top_shap_features} />
                )}
              </CardContent>
            </Card>
          )
        )}

        {/* ---- Counterfactual ---- */}
        {detail && detail.counterfactual && detail.counterfactual.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>What would change this decision</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {detail.counterfactual.map((c) => (
                <p key={c.feature} className="text-sm leading-relaxed">
                  {c.required_value !== null ? (
                    <>
                      If <span className="text-foreground">{c.feature.replace(/_/g, " ")}</span>{" "}
                      changed from{" "}
                      <span className="tabular-nums text-red-300">{c.current_value}</span> to{" "}
                      <span className="tabular-nums text-emerald-300">{c.required_value}</span>,
                      this application would move to a lower-risk band.
                    </>
                  ) : (
                    <span className="text-muted-foreground">
                      Changing {c.feature.replace(/_/g, " ")} alone (currently{" "}
                      <span className="tabular-nums">{c.current_value}</span>) cannot cross the
                      decision boundary — the risk is driven by multiple factors together.
                    </span>
                  )}
                </p>
              ))}
            </CardContent>
          </Card>
        )}

        {/* ---- Ring ---- */}
        <RingPanel ring={ring} loading={!ring && !ringError} error={ringError} />

        {/* ---- Similar past cases ---- */}
        <SimilarCasesPanel
          data={similar}
          loading={!similar && !similarError}
          error={similarError}
        />

        {/* ---- Feedback ---- */}
        {id && <FeedbackPanel applicationId={id} />}
      </main>
    </div>
  );
}
