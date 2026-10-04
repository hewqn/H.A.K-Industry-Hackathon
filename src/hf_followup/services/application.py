"""Read-only local vertical slice: the backend owner's starting point.

Snapshots here live in memory and vanish on restart. Implement the PRD §25 durable
command/event protocol through Repository before enabling workflow mutations. This
service receives allowlisted features and aggregate reports, never historical labels.
"""

import uuid
from datetime import UTC, datetime

from hf_followup.domain.constants import INDICATOR_POLICY, METHODS, UNITS
from hf_followup.domain.errors import DomainError
from hf_followup.domain.indicators import organ_indicators
from hf_followup.domain.ranking import build_ranking
from hf_followup.repositories.bundle import digest
from hf_followup.services.summaries import template_summary


class ApplicationService:
    def __init__(self, cohort, benchmark: dict, settings):
        self.cohort, self.benchmark, self.settings = cohort, benchmark, settings
        self.snapshots = {}
        self.default_snapshot = self.create_snapshot("points_v1", 25)

    def create_snapshot(self, method_id: str, capacity: int, mode="operational") -> dict:
        # TODO(BACKEND, OPS-01): persist immutable snapshots and provenance in application_events.
        ranking = build_ranking(self.cohort.features, {}, {}, method_id, capacity, mode=mode)
        snapshot = {
            **ranking,
            "snapshot_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "cohort_id": self.cohort.manifest["cohort_id"],
            "source_hash": self.cohort.manifest["source_hash"],
            "session_id": self.settings.session_id,
            "workflow_revision": 0,
            "workflow": {},
            "overrides": {},
            "provenance": "local_csv_scaffold",
            "sync_mode": "in_memory_scaffold",
        }
        self.snapshots[snapshot["snapshot_id"]] = snapshot
        return snapshot

    def snapshot(self, snapshot_id: str) -> dict:
        if snapshot_id not in self.snapshots:
            raise DomainError(
                "snapshot_not_found", "Snapshot does not exist; refresh after an API restart.", 404
            )
        return self.snapshots[snapshot_id]

    def cohort_read(self) -> dict:
        return {
            **self.cohort.manifest,
            "eligible_count": len(self.cohort.features),
            "workflow_revision": 0,
            "current_snapshot_id": self.default_snapshot["snapshot_id"],
            "session_id": self.settings.session_id,
            "provenance": "local_csv_scaffold",
            "sync_mode": "in_memory_scaffold",
        }

    def models(self) -> dict:
        # TODO(ML): add frozen prediction lookup and labelled CV/test reports through Repository.
        return {
            "methods": [
                {
                    "method_id": method,
                    "label": method.replace("_", " "),
                    "score_kind": "points" if method.startswith("points") else "model_output",
                }
                for method in METHODS
            ],
            "reports": {"benchmark": self.benchmark},
            "supervised_status": "awaiting_ml_owner",
        }

    def patient(self, patient_id: str, snapshot_id: str) -> dict:
        if patient_id not in self.cohort.features:
            raise DomainError(
                "patient_not_found", "Patient does not exist in the bundled cohort.", 404
            )
        snapshot = self.snapshot(snapshot_id)
        row = next(row for row in snapshot["rows"] if row["patient_id"] == patient_id)
        facts = row["facts"]
        measurements = [
            {
                "id": "ef_measurement",
                "field": "ejection_fraction",
                "value": facts["ejection_fraction"],
                "unit": "%",
                "predicate": "recorded EF",
                "scale": "measurement",
            },
            {
                "id": "creatinine_measurement",
                "field": "serum_creatinine",
                "value": facts["serum_creatinine"],
                "unit": "mg/dL",
                "predicate": "recorded creatinine",
                "scale": "measurement",
            },
        ]
        patient = {
            "patient_id": patient_id,
            "cohort_id": snapshot["cohort_id"],
            "ranking_snapshot_id": snapshot_id,
            "method_id": snapshot["method_id"],
            "model_rank": row["model_rank"],
            "call_rank": row["call_rank"] if row["in_queue"] else None,
            "priority_band": row["priority_band"],
            "score": row["score"],
            "facts": facts,
            "evidence": [*measurements, *row["score"]["evidence"]],
            "organs": organ_indicators(facts),
            "indicator_policy_version": INDICATOR_POLICY,
            "explanation_method": row["score"]["explanation_method"],
            "workflow": {"state": "pending", "revision": 0},
            "override": None,
            "provenance": "local_csv_scaffold",
            "summary_status": "template",
            "fact_units": UNITS,
        }
        patient["evidence_digest"] = digest(patient)
        patient["summary"] = template_summary(patient)
        # TODO(SUM-01): validated provider adapter + cache by digest/prompt/generator versions.
        return patient
