import type { Patient } from "../src/types/patient";

export function riskEnvelope(heart = 0.2, kidney = 0.8, patient = 0.7): NonNullable<Patient["model_risks"]> {
  const estimate = (score: number) => ({
    score, band: score < 0.33 ? "lower" as const : score < 0.66 ? "middle" as const : "higher" as const,
    classification_positive: score >= 0.5, classification_threshold: 0.5,
    model_family: "random_forest" as const, model_version: "frozen-test-v1",
    score_kind: "model_output" as const, calibration_status: "not_calibrated" as const,
    prediction_provenance: "new_patient_inference" as const,
    explanation_method: "recorded_features_no_local_attribution" as const, evidence: [], intercept: null,
  });
  return { bundle_id: "hf-0123456789abcdef0123", heart_risk: estimate(heart), kidney_risk: estimate(kidney), patient_risk: estimate(patient) };
}
