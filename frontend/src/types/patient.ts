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
  score_kind: "points" | "model_output";
  /** 0–1 per organ. Points placeholder now; replace with model output later. */
  organ_risk: {
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
