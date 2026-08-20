import { ArrowLeft, FileText, GitBranch, Lightbulb, Scale, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BandBadge } from "@/components/BandBadge";
import BorderGlow from "@/components/reactbits/BorderGlow";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { IdentityPanel } from "@/components/IdentityPanel";
import { InvestigationPanel } from "@/components/InvestigationPanel";
import { Navbar } from "@/components/Navbar";
import { RingPanel } from "@/components/RingPanel";
import { ShapChart } from "@/components/ShapChart";
import { SimilarCasesPanel } from "@/components/SimilarCasesPanel";
import { ApplicantView } from "@/components/reports/ApplicantView";
import { RegulatorView } from "@/components/reports/RegulatorView";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TitleIcon } from "@/components/ui/title-icon";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  ApplicantReport,
  ApplicationDetail as AppDetail,
  RegulatorReport,
  RingInfo,
  SimilarCasesResponse,
} from "@/lib/types";
import { stagger } from "@/lib/motion";
import { formatMoney, formatTime } from "@/lib/utils";

type Audience = "investigator" | "regulator" | "applicant";
type LoadState = "idle" | "loading" | "done";

const AUDIENCES: { key: Audience; label: string; icon: typeof FileText }[] = [
  { key: "investigator", label: "Investigator View", icon: FileText },
  { key: "regulator", label: "Regulator View", icon: Scale },
  { key: "applicant", label: "Applicant Notice", icon: UserRound },
];

/**
 * Decision-summary frame. SpotlightCard always; BorderGlow layered only for
 * AUTO_FLAG so the glow itself is the signal, not ornament.
 */
function DecisionSummaryFrame({
  band,
  children,
}: {
  band: string | null;
  children: React.ReactNode;
}) {
  const spotlight = (
    <SpotlightCard
      className="aegis-surface overflow-hidden rounded-xl"
      spotlightColor="rgba(219, 234, 254, 0.10)"
    >
      {children}
    </SpotlightCard>
  );

  if (band !== "AUTO_FLAG") return spotlight;

  return (
    <BorderGlow
      glowColor="0 84 60"
      glowIntensity={0.7}
      fillOpacity={0.22}
      borderRadius={14}
      glowRadius={30}
      animated={false}
      colors={["#EF4444", "#F87171", "#B91C1C"]}
      backgroundColor="hsl(218 49% 10%)"
    >
      {spotlight}
    </BorderGlow>
  );
}

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();

  const [detail, setDetail] = useState<AppDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [ring, setRing] = useState<RingInfo | null>(null);
  const [ringError, setRingError] = useState<string | null>(null);
  const [similar, setSimilar] = useState<SimilarCasesResponse | null>(null);
  const [similarError, setSimilarError] = useState<string | null>(null);

  // Audience lens. Switching tabs never refetches the application itself —
  // it is one decision viewed three ways. Each report is fetched on first
  // open only and cached in state for the session.
  const [audience, setAudience] = useState<Audience>("investigator");
  const [regulator, setRegulator] = useState<RegulatorReport | null>(null);
  const [regulatorState, setRegulatorState] = useState<LoadState>("idle");
  const [regulatorError, setRegulatorError] = useState<string | null>(null);
  const [applicant, setApplicant] = useState<ApplicantReport | null>(null);
  const [applicantState, setApplicantState] = useState<LoadState>("idle");
  const [applicantError, setApplicantError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    if (audience === "regulator" && regulatorState === "idle") {
      setRegulatorState("loading");
      api
        .getRegulatorReport(id)
        .then((r) => {
          setRegulator(r);
          setRegulatorState("done");
        })
        .catch((e) => {
          setRegulatorError(e.message);
          setRegulatorState("done");
        });
    }
    if (audience === "applicant" && applicantState === "idle") {
      setApplicantState("loading");
      api
        .getApplicantReport(id)
        .then((r) => {
          setApplicant(r);
          setApplicantState("done");
        })
        .catch((e) => {
          setApplicantError(e.message);
          setApplicantState("done");
        });
    }
  }, [audience, id, regulatorState, applicantState]);

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
          <p className="text-sm text-danger">Could not load this application — {detailError}</p>
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
      <main className="mx-auto max-w-5xl space-y-4 px-4 py-5 sm:px-6">
        <Link
          to="/dashboard"
          className="report-noprint inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Back to dashboard
        </Link>

        {/* ---- Audience switcher: same decision, three lenses ---- */}
        <div className="report-tabs report-noprint flex flex-wrap items-center gap-1 rounded-xl border border-border bg-card p-1">
          {AUDIENCES.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setAudience(key)}
              aria-current={audience === key ? "page" : undefined}
              className={`inline-flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                audience === key
                  ? "bg-brand/10 text-brand"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" strokeWidth={2} />
              {label}
            </button>
          ))}
        </div>

        {audience === "regulator" && (
          <RegulatorView
            report={regulator}
            loading={regulatorState !== "done"}
            error={regulatorError}
          />
        )}

        {audience === "applicant" && (
          <ApplicantView
            report={applicant}
            loading={applicantState !== "done"}
            error={applicantError}
          />
        )}

        {audience === "investigator" && (
        <>

        {/* ---- (1) Decision summary ----
             The ONLY card in the app with the SpotlightCard treatment, and the
             ONLY place BorderGlow appears — and only when the band is
             AUTO_FLAG, so the red glow carries meaning ("this case is high
             risk") rather than decorating. */}
        {!detail ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <DecisionSummaryFrame band={decision?.decision_band ?? null}>
            <Card className="aegis-enter !border-0 !bg-transparent !shadow-none">
            <CardContent className="p-5 sm:p-6">
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
          </DecisionSummaryFrame>
        )}

        {/* ---- (2) Why flagged: SHAP explanation ---- */}
        {!detail ? (
          <Skeleton className="h-72 w-full" />
        ) : (
          decision && (
            <Card className="aegis-enter" style={stagger(1)}>
              <CardHeader>
                <CardTitle>
                  <TitleIcon icon={Lightbulb} tone="brand" />
                  Why the model decided this
                </CardTitle>
                <p className="aegis-section-desc mt-1">Model factors ranked by contribution to this score</p>
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
          <Card className="aegis-enter" style={stagger(2)}>
            <CardHeader>
              <CardTitle>
                <TitleIcon icon={GitBranch} tone="success" />
                What would change this decision
              </CardTitle>
              <p className="aegis-section-desc mt-1">Smallest single-factor change that reaches a lower-risk band</p>
            </CardHeader>
            <CardContent className="space-y-2">
              {detail.counterfactual.map((c) => (
                <p key={c.feature} className="text-sm leading-relaxed">
                  {c.required_value !== null ? (
                    <>
                      If <span className="text-foreground">{c.feature.replace(/_/g, " ")}</span>{" "}
                      changed from{" "}
                      <span className="tabular-nums text-danger">{c.current_value}</span> to{" "}
                      <span className="tabular-nums text-success">{c.required_value}</span>,
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

        {/* ---- Identity verification (ID modality) ---- */}
        {detail && (
          <div className="aegis-enter" style={stagger(3)}>
          <IdentityPanel
            identityCheck={detail.identity_check}
            idDocumentFilename={detail.id_document_filename}
          />
          </div>
        )}

        {/* ---- Ring ---- */}
        <div className="aegis-enter" style={stagger(4)}>
          <RingPanel ring={ring} loading={!ring && !ringError} error={ringError} />
        </div>

        {/* ---- Similar past cases ---- */}
        <div className="aegis-enter" style={stagger(5)}>
          <SimilarCasesPanel
            data={similar}
            loading={!similar && !similarError}
            error={similarError}
          />
        </div>

        {/* ---- AI investigation agent ---- */}
        {id && (
          <div className="aegis-enter" style={stagger(6)}>
            <InvestigationPanel applicationId={id} />
          </div>
        )}

        {/* ---- (7) Investigator action ---- */}
        {id && (
          <div className="aegis-enter" style={stagger(7)}>
            <FeedbackPanel applicationId={id} />
          </div>
        )}
        </>
        )}
      </main>
    </div>
  );
}
