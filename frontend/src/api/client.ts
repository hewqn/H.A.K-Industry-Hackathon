import type { components } from "./generated";

// Generated from Pydantic/OpenAPI: edit the backend schema and run make types.
export type Patient = components["schemas"]["PatientRead"];
export type Snapshot = components["schemas"]["Snapshot"];
export type Cohort = components["schemas"]["CohortRead"];
export type Mutation = components["schemas"]["MutationResult"];
export type OrganId = "heart" | "kidney_left" | "kidney_right";

export interface Method { method_id: string; label: string; score_kind: string }
export interface Metrics { n: number; k: number; captured_outcomes: number; precision_at_k: number; capture_at_k: number; roc_auc?: number }
export interface ModelReport {
  evaluation_mode: string; development_n: number; test_n: number; winner: string; test: Metrics;
  candidates: { candidate_id: string; family: string; mean: Metrics; std: Metrics }[];
  baselines: Record<string, { mean: Metrics; test: Metrics }>;
  descriptive_full_cohort: Metrics;
}
export interface Benchmark {
  evaluation_mode: string; tie_policy: string; metrics: Record<string, Metrics>; overlap_count: number;
  decision: string; reason: string;
  movements: { patient_id: string; baseline_rank: number; candidate_rank: number; rank_delta: number; score_delta: number; membership: string; reason: string }[];
}
export interface Models { methods: Method[]; reports: { benchmark: Benchmark; supervised?: ModelReport } }
export interface Audit { event_id: string; action: string; patient_id: string | null; reason: string | null; revision: number; created_at: string; sync_status: string }
export interface Health { mode: string; voice: string; pending_sync: number; provenance: string }
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
  const response = await fetch(`/api/v1${path}`, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ code: "connection_failed", message: "API request failed." }));
    throw new ApiError(error.code, error.message, response.status);
  }
  return response.json() as Promise<T>;
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const command = (revision: number) => ({ command_id: crypto.randomUUID(), expected_revision: revision });
