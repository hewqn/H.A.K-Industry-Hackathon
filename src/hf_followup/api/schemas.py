"""Versioned request/read contracts. Unknown request fields are rejected, not executed."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hf_followup.domain.constants import COHORT_ID
from hf_followup.domain.predictions import ModelFamily, ModelRisks, RiskTask


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Command(Request):
    command_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)


class SnapshotRequest(Command):
    cohort_id: str = COHORT_ID
    method_id: str = Field(default="points_v1", max_length=100)
    capacity: int = Field(default=25, ge=1, le=50, strict=True)
    mode: Literal["operational", "benchmark"] = "operational"


class WorkflowRequest(Command):
    state: Literal["pending", "reviewed", "contacted", "needs_clinician_review"]
    reason: str | None = Field(default=None, max_length=1000)


class OverrideRequest(Command):
    patient_id: str = Field(pattern=r"^HF-\d{4}$")
    session_id: str = Field(max_length=100)
    action: Literal["pin", "defer", "reset"]
    reason: str = Field(min_length=1, max_length=1000)


class ResetRequest(Command):
    reason: str = Field(min_length=1, max_length=1000)


class ContextRequest(Request):
    snapshot_id: str = Field(max_length=100)
    patient_id: str | None = Field(default=None, pattern=r"^HF-\d{4}$")


class SummaryRequest(Request):
    snapshot_id: str = Field(max_length=100)
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ComparisonRequest(Request):
    cohort_id: str = COHORT_ID


class ToolRequest(ContextRequest):
    limit: int = Field(default=5, ge=1, le=5)
    report_id: str = "case-benchmark-v1"
    cohort_id: str = COHORT_ID


class Facts(BaseModel):
    # Explicit response allowlist prevents evaluation fields from leaking by accident.
    model_config = ConfigDict(extra="forbid")
    age: float
    anaemia: bool
    creatinine_phosphokinase: float
    diabetes: bool
    ejection_fraction: float
    high_blood_pressure: bool
    platelets: float
    serum_creatinine: float
    serum_sodium: float
    sex: bool
    smoking: bool


class Evidence(BaseModel):
    id: str
    field: str
    value: float | bool
    unit: str | None = None
    predicate: str
    scale: str
    points: float | None = None
    contribution: float | None = None


class Score(BaseModel):
    value: float
    kind: Literal["points", "model_output", "calibrated_probability"]
    label: str
    evidence: list[Evidence]
    explanation_method: str
    version: str
    prediction_provenance: str | None = None
    intercept: float | None = None
    calibration_status: str | None = None


class OrganIndicator(BaseModel):
    state: Literal["flagged", "not_flagged", "unknown"]
    value: float | None
    unit: Literal["%", "mg/dL"]
    label: str
    evidence_ids: list[str]


class Organs(BaseModel):
    heart: OrganIndicator
    kidney_left: OrganIndicator
    kidney_right: OrganIndicator


class Workflow(BaseModel):
    state: Literal["pending", "reviewed", "contacted", "needs_clinician_review"]
    revision: int


class Override(BaseModel):
    action: Literal["pin", "defer"]
    reason: str
    sequence: int
    actor: str


class Summary(BaseModel):
    patient_id: str
    evidence_digest: str
    text: str
    evidence_ids: list[str]
    limitations: list[str]
    status: str
    prompt_version: str
    generator_version: str


class QueueRow(BaseModel):
    patient_id: str
    model_rank: int
    call_rank: int
    in_queue: bool
    priority_band: str
    score: Score
    facts: Facts
    reason: str
    workflow_state: str
    override: Override | None


class Snapshot(BaseModel):
    snapshot_id: str
    cohort_id: str
    source_hash: str
    created_at: str
    session_id: str
    workflow_revision: int
    method_id: str
    capacity: int
    mode: str
    eligible_count: int
    selected_count: int
    tie_policy: str
    rows: list[QueueRow]
    queue: list[QueueRow]
    workflow: dict[str, str]
    overrides: dict[str, Override]
    provenance: str
    sync_mode: str
    model_bundle_id: str | None = None


class MutationResult(BaseModel):
    snapshot: Snapshot
    revision: int
    sync_status: str
    replayed: bool


class PatientRead(BaseModel):
    patient_id: str
    cohort_id: str
    ranking_snapshot_id: str
    method_id: str
    model_rank: int | None
    call_rank: int | None
    priority_band: str
    score: Score
    facts: Facts
    evidence: list[Evidence]
    organs: Organs
    indicator_policy_version: str
    explanation_method: str
    workflow: Workflow
    override: Override | None
    provenance: str
    summary_status: str
    fact_units: dict[str, str]
    evidence_digest: str
    summary: Summary
    model_risks: ModelRisks | None = None


class ModelDescriptor(BaseModel):
    family: ModelFamily
    model_version: str
    features: list[str]
    classification_threshold: float = Field(ge=0, le=1)
    band_cutoffs: dict[str, float]
    explanation_method: str
    calibration_status: Literal["not_calibrated"]


class MethodRead(BaseModel):
    method_id: str
    label: str
    score_kind: str
    available: bool


class ModelsRead(BaseModel):
    methods: list[MethodRead]
    reports: dict[str, Any]
    supervised_status: Literal["ready", "not_published"]
    bundle_id: str | None
    selected_models: dict[RiskTask, ModelDescriptor]


class CohortRead(BaseModel):
    cohort_id: str
    source_hash: str
    schema_version: str
    accepted_ids: list[str]
    accepted_count: int
    source_count: int
    excluded_count: int
    missing_rows: int
    missing_cells: int
    exclusions: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    feature_allowlist: list[str]
    source: str
    license: str
    eligible_count: int
    workflow_revision: int
    current_snapshot_id: str | None
    session_id: str
    provenance: str
    sync_mode: str
