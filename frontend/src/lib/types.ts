export type DecisionBand = "AUTO_APPROVE" | "HUMAN_REVIEW" | "AUTO_FLAG";

export interface ApplicationSummary {
  id: string;
  created_at: string;
  applicant_age: number;
  annual_income: number;
  employment_type: string;
  requested_amount: number;
  loan_purpose: string;
  device_id: string;
  calibrated_risk_score: number | null;
  decision_band: DecisionBand | null;
}

export interface ApplicationList {
  total: number;
  limit: number;
  offset: number;
  items: ApplicationSummary[];
}

export interface ShapFeature {
  feature: string;
  label: string;
  value: number;
  shap_value: number;
  direction: "increases_risk" | "decreases_risk";
  explanation: string;
}

export interface Counterfactual {
  feature: string;
  current_value: number;
  required_value: number | null;
  would_change_decision_to: string | null;
  note?: string | null;
}

export interface Decision {
  id: string;
  model_version: string;
  xgboost_probability: number;
  anomaly_score: number;
  calibrated_risk_score: number;
  decision_band: DecisionBand;
  explanation_text: string;
  explanation_source?: string | null;
  ring_size: number;
  ring_risk_score: number;
  network_hits?: NetworkHit[] | null;
  identity_continuity?: IdentityContinuity | null;
  step_up_result?: StepUpResult | null;
  latency_ms: number;
  created_at: string;
}

export interface IdentityCheck {
  applicant_name: string | null;
  id_document_name: string | null;
  mismatch: boolean;
  form_dob?: string | null;
  ocr_dob?: string | null;
  ocr_id_number?: string | null;
  reused_across_names?: boolean;
  prior_names?: string[];
  prior_uses?: number;
}

export interface SampleId {
  filename: string;
  applicant_name: string;
  id_name: string;
  mismatch: boolean;
  image_url: string;
}

export interface ApplicationDetail {
  id: string;
  created_at: string;
  applicant_age: number;
  annual_income: number;
  employment_type: string;
  employer_name: string;
  requested_amount: number;
  loan_purpose: string;
  loan_purpose_text: string;
  device_id: string;
  ip_hash: string;
  session_duration_seconds: number;
  mouse_movement_events: number;
  form_paste_count: number;
  id_document_filename: string | null;
  decision: Decision | null;
  top_shap_features: ShapFeature[];
  counterfactual: Counterfactual[] | null;
  connected_applications: string[];
  identity_check: IdentityCheck | null;
}

export interface RingMember {
  application_id: string;
  decision_band: DecisionBand | null;
  source: "database" | "historical";
}

export interface RingInfo {
  application_id: string;
  ring_size: number;
  ring_risk_score: number;
  members: RingMember[];
}

export interface SimilarCase {
  case_id: string;
  fraud_type: string;
  narrative_text: string;
  similarity_score: number;
}

export interface SimilarCasesResponse {
  query_text: string;
  matches: SimilarCase[];
  summary: string;
  summary_source: string;
}

export interface DriftFeature {
  feature: string;
  psi: number;
  status: string;
  reference_mean: number;
  recent_mean: number;
}

export interface DriftResponse {
  overall_drift_status:
    | "STABLE"
    | "MILD_DRIFT"
    | "SIGNIFICANT_DRIFT"
    | "INSUFFICIENT_DATA";
  recent_applications: number;
  window_hours: number;
  computed_at: string;
  features: DriftFeature[];
  summary: string;
}

export interface ScoreRequest {
  applicant_age: number;
  annual_income: number;
  employment_type: string;
  employer_name: string;
  requested_amount: number;
  loan_purpose: string;
  loan_purpose_text: string;
  device_id: string;
  ip_hash: string;
  session_duration_seconds: number;
  mouse_movement_events: number;
  form_paste_count: number;
  id_document_filename?: string | null;
  applicant_name?: string | null;
  id_document_uploaded_name?: string | null;
  applications_from_device_last_24h?: number | null;
  applications_from_ip_last_24h?: number | null;
  income_employer_consistency_score: number;
  identity_consistency_score: number;
}

export interface ScoreResponse {
  application_id: string;
  decision: Decision;
  top_shap_features: ShapFeature[];
  counterfactual: Counterfactual[] | null;
  connected_applications: string[];
}

export interface FeedbackResponse {
  id: string;
  decision_id: string;
  investigator_username: string;
  verdict: string;
  notes: string | null;
  created_at: string;
}

export interface InvestigationStep {
  step: string;
  description: string;
  timestamp: string;
}

/** Layer 5 — identity continuity verdict stored on the decision. */
export interface IdentityContinuity {
  status: "NO_HISTORY" | "CONSISTENT" | "INCONSISTENT";
  prior_observations: number;
  baseline_observations?: number;
  changed_signals: string[];
  detail: string;
  step_up_available?: boolean;
  registered_contact?: string | null;
}

export interface StepUpResult {
  outcome: "CORRECT" | "INCORRECT";
  masked_contact: string;
  risk_delta: number;
  risk_before: number;
  risk_after: number;
  band_before: string;
  band_after: string;
}

/** Institutional-memory agreement verdict attached to an investigation. */
export interface MemoryAlignment {
  stance: "supports" | "conflicts" | "neutral";
  matched: number;
  confirmed_fraud: number;
  confirmed_legitimate: number;
  case_leaning: string;
  note: string | null;
  confidence_effect: string;
}

export interface InvestigationResponse {
  application_id: string;
  investigation_log: InvestigationStep[];
  recommended_action: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasoning_summary: string;
  synthesis_source: string;
  memory_alignment?: MemoryAlignment | null;
  cached: boolean;
  created_at: string;
}

// ---- Multi-audience reports -------------------------------------------------

export interface ProvenanceStep {
  step: number;
  stage: string;
  detail: string;
}

export interface ContributingFactor {
  factor: string;
  label: string;
  direction: string;
  contribution: number;
  description: string;
  basis: string;
}

export interface RegulatorReport {
  report_version: string;
  report_generated_at: string;
  decision_summary: {
    application_id: string;
    timestamp: string;
    decision_band: string;
    calibrated_risk_score: number;
    model_version: string;
    scoring_latency_ms: number;
  };
  fair_lending_disclosure: {
    prohibited_bases_excluded: string[];
    attestation: string;
    feature_specification_reference: string;
  };
  decision_provenance: ProvenanceStep[];
  top_contributing_factors: ContributingFactor[];
  model_governance: Record<string, string>;
  human_review_status: {
    reviewed: boolean;
    status: string;
    verdict: string | null;
    reviewed_at: string | null;
    reviewer: string | null;
    notes: string | null;
  };
  audit_trail_reference: {
    application_id: string;
    audit_log_entry_count: number;
    cross_reference_note: string;
  };
  data_disclosure: string;
}

export interface ApplicantReport {
  reference_number: string;
  decision_date: string;
  decision_outcome: string;
  primary_reasons: string[];
  what_you_can_do: string[];
  your_rights: string[];
  appeal_reference_code: string;
  contact_note: string;
  report_generated_at: string;
  data_disclosure: string;
}

// ---- Aegis Network ----------------------------------------------------------

export interface NetworkHit {
  signal_type: string;
  matched_hash_prefix: string;
  reported_by: string;
  reported_by_code: string;
  fraud_confirmed_at: string;
  notes: string | null;
}

export interface NetworkStats {
  member_institutions: number;
  total_signals: number;
  signals_last_24h: number;
  prevented_attacks: number;
  by_institution: { code: string; display_name: string; signals_published: number }[];
}

export interface NetworkSignalRow {
  signal_type: string;
  hash_prefix: string;
  reported_by: string;
  reported_by_code: string;
  fraud_confirmed_at: string;
  created_at: string;
  notes: string | null;
}

export interface NetworkSignalsResponse {
  privacy_note: string;
  signals: NetworkSignalRow[];
}

export interface NetworkGraph {
  nodes: { id: string; label: string; signals_published: number }[];
  links: { source: string; target: string; shared_signal_hits: number }[];
}
