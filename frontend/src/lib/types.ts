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
  latency_ms: number;
  created_at: string;
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
