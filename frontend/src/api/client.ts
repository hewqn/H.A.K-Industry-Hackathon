import type { components } from "./generated";

// Generated from Pydantic/OpenAPI: edit the backend schema and run make types.
export type Patient = components["schemas"]["PatientRead"];
export type Snapshot = components["schemas"]["Snapshot"];
export type Cohort = components["schemas"]["CohortRead"];
export type Mutation = components["schemas"]["MutationResult"];
export type OrganId = "heart" | "kidney_left" | "kidney_right";

export interface Method { method_id: string; label: string; score_kind: string }
export interface Metrics { n: number; k: number; captured_outcomes: number; precision_at_k: number; capture_at_k: number; roc_auc?: number }
export type RiskTask = "heart_risk" | "kidney_risk" | "patient_risk";
export type RiskEstimate = components["schemas"]["RiskEstimate"];
export interface Counts { tn: number; fp: number; fn: number; tp: number }
export interface ClassificationMetrics { counts: Counts; confusion_matrix: number[][]; classification_report: Record<string, unknown> }
export interface ModelEvaluation extends ClassificationMetrics {
  best_params: Record<string, string | number | null>;
  development_threshold: number;
  development_oof: ClassificationMetrics;
  thresholded: ClassificationMetrics;
  test: Metrics;
}
export interface SupervisedReport {
  evaluation_mode: "exploratory_held_out_test";
  development_n: number;
  test_n: number;
  selection: string;
  limitations: string[];
  tasks: Record<RiskTask, {
    selected_family: RiskEstimate["model_family"];
    selected_threshold: number;
    selection_development_counts: Counts;
    models: Record<string, ModelEvaluation>;
  }>;
}
export interface Benchmark {
  evaluation_mode: string; tie_policy: string; metrics: Record<string, Metrics>; overlap_count: number;
  decision: string; reason: string;
  movements: { patient_id: string; baseline_rank: number; candidate_rank: number; rank_delta: number; score_delta: number; membership: string; reason: string }[];
}
export type Models = Omit<components["schemas"]["ModelsRead"], "reports"> & {
  reports: { benchmark: Benchmark; supervised: SupervisedReport | null };
};
export interface Audit { event_id: string; action: string; patient_id: string | null; reason: string | null; revision: number; created_at: string; sync_status: string }
export interface Health {
  core?: string;
  mode?: string;
  databricks?: string;
  voice: string;
  persistence?: string;
  ml?: string;
  model_bundle_id?: string | null;
  pending_sync?: number;
  provenance?: string;
}
// Keep the full generated private-session contract, including expiring tool grants.
export type VoiceContext = components["schemas"]["VoiceContextRead"];
export type VoiceSession = components["schemas"]["VoiceSessionRead"];

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem("hak-token");
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ code: "connection_failed", message: "API request failed." }));
    if (response.status === 401 && !path.startsWith("/auth/")) {
      sessionStorage.removeItem("hak-token");
      sessionStorage.removeItem("hak-role");
      window.dispatchEvent(new Event("hak-auth-lost"));
    }
    throw new ApiError(error.code, error.message, response.status);
  }
  return response.json() as Promise<T>;
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const command = (revision: number) => ({ command_id: crypto.randomUUID(), expected_revision: revision });
