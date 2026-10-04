import type { components } from "../api/generated";

export type OrganId = "heart" | "kidney_left" | "kidney_right";
export type IndicatorState = "flagged" | "not_flagged" | "unknown";
export type PriorityBand = "higher" | "elevated" | "lower";
export type WorkflowState = "pending" | "reviewed" | "contacted" | "needs_clinician_review";

export interface OrganIndicator {
  state: IndicatorState;
  value: number | null;
  unit: "%" | "mg/dL";
  label: string;
}

export interface Patient {
  patient_id: string;
  rank: number;
  oldest_rank: number;
  priority_band: PriorityBand;
  score: number;
  score_kind: "points" | "model_output" | "age" | "combined";
  /** Pure ML rank (set when score_kind is "combined"). */
  model_rank?: number;
  /** Browser combination = patient model score + normalized rule points (0–2). */
  combined_score?: number;
  /** Shared versioned ML interface; scores are uncalibrated outcome proxies. */
  model_risks?: components["schemas"]["ModelRisks"] | null;
  /** Frozen ML heart_risk / kidney_risk. Used only by Risk Score colour. */
  organ_risk?: {
    heart: number;
    kidney: number;
  };
  facts: {
    age: number;
    ejection_fraction: number;
    serum_creatinine: number;
    anaemia: boolean;
    diabetes: boolean;
    high_blood_pressure: boolean;
    creatinine_phosphokinase: number;
    platelets: number;
    serum_sodium: number;
    sex: number;
    smoking: boolean;
  };
  organs: Record<OrganId, OrganIndicator>;
  evidence: EvidenceItem[];
  /** Later DEATH_EVENT from the labelled UCI file. Missing for live add-ons. */
  later_death?: boolean | null;
  workflow_state: WorkflowState;
  summary?: string;
}

export interface EvidenceItem {
  id: string;
  field: string;
  value: number | boolean;
  unit?: string;
  points?: number;
  description: string;
}

export interface RankingSnapshot {
  id: string;
  method: string;
  capacity: number;
  patients: Patient[];
  timestamp: string;
}
