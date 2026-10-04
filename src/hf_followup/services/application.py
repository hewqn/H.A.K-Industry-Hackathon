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
    def __init__(self, cohort, benchmark: dict, settings, prediction_bundle=None):
        self.cohort, self.benchmark, self.settings = cohort, benchmark, settings
        self.prediction_bundle = prediction_bundle
        self.predictions = prediction_bundle.ranking_predictions() if prediction_bundle else {}
        self.snapshots = {}
        default_method = settings.default_method
        if default_method == "auto":
            default_method = "patient_risk" if prediction_bundle else "points_v1"
        self.default_snapshot = self.create_snapshot(default_method, 25)

    def create_snapshot(self, method_id: str, capacity: int, mode="operational") -> dict:
        # TODO(BACKEND, OPS-01): persist immutable snapshots and provenance in application_events.
        ranking = build_ranking(
            self.cohort.features,
            {},
            {},
            method_id,
            capacity,
            mode=mode,
            predictions=self.predictions,
        )
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
            "model_bundle_id": self.prediction_bundle.manifest["bundle_id"]
            if self.prediction_bundle
            else None,
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
        manifest = self.prediction_bundle.manifest if self.prediction_bundle else None
        supervised = None
        if self.prediction_bundle:
            report = self.prediction_bundle.report
            supervised = {
                "evaluation_mode": "exploratory_held_out_test",
                "development_n": len(report["split"]["development_ids"]),
                "test_n": len(report["split"]["test_ids"]),
                "selection": report["selection"],
                "tasks": report["tasks"],
                "limitations": report["limitations"],
            }
        return {
            "methods": [
                {
                    "method_id": method,
                    "label": method.replace("_", " "),
                    "score_kind": "points" if method.startswith("points") else "model_output",
                    "available": True,
                }
                for method in (*METHODS, *self.predictions)
            ],
            "reports": {"benchmark": self.benchmark, "supervised": supervised},
            "supervised_status": "ready" if manifest else "not_published",
            "bundle_id": manifest["bundle_id"] if manifest else None,
            "selected_models": manifest["models"] if manifest else {},
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
            "model_risks": self.prediction_bundle.patients[patient_id]["risks"]
            if self.prediction_bundle
            else None,
        }
        # One evidence namespace for summaries/tools. Logistic entries are real scaled
        # log-odds contributions; forest entries are observations, not local attribution.
        if patient["model_risks"]:
            evidence = {item["id"]: item for item in patient["evidence"]}
            for task in self.prediction_bundle.manifest["models"]:
                evidence.update(
                    {item["id"]: item for item in patient["model_risks"][task]["evidence"]}
                )
            patient["evidence"] = list(evidence.values())
        patient["evidence_digest"] = digest(patient)
        patient["summary"] = template_summary(patient)
        # TODO(SUM-01): validated provider adapter + cache by digest/prompt/generator versions.
        return patient
