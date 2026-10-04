"""Shared ML read contract for Python, HTTP, database rows and the 3D handoff.

These are three recorded-outcome proxies, not organ diagnoses or calibrated risks.
The classifier threshold and the relative band boundaries serve different purposes.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RISK_TASKS = ("heart_risk", "kidney_risk", "patient_risk")
RiskTask = Literal["heart_risk", "kidney_risk", "patient_risk"]
ModelFamily = Literal["logistic_regression", "random_forest", "gradient_boosting"]


class RiskEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    field: str
    value: float | bool
    unit: str | None = None
    predicate: str
    scale: Literal["log_odds", "recorded_measurement"]
    contribution: float | None = None


class RiskEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    score: float = Field(ge=0, le=1)
    band: Literal["lower", "middle", "higher"]
    classification_positive: bool
    classification_threshold: float = Field(ge=0, le=1)
    model_family: ModelFamily
    model_version: str
    score_kind: Literal["model_output"] = "model_output"
    calibration_status: Literal["not_calibrated"] = "not_calibrated"
    prediction_provenance: Literal[
        "development_in_sample", "held_out_test", "new_patient_inference"
    ]
    explanation_method: Literal["linear_log_odds", "recorded_features_no_local_attribution"]
    evidence: list[RiskEvidence]
    intercept: float | None = None


class ModelRisks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: str = Field(pattern=r"^hf-[0-9a-f]{20}$")
    heart_risk: RiskEstimate
    kidney_risk: RiskEstimate
    patient_risk: RiskEstimate
