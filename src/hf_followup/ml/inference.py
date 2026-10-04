"""Pure inference from trusted frozen pipelines; never fits or queries outcome labels.

Use RiskPredictor for new baseline records/batch publication. The API consumes its
JSON cache instead. Do not load joblib artifacts uploaded by arbitrary users.
"""

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from hf_followup.domain.constants import BINARY_FIELDS, FEATURES, UNITS
from hf_followup.domain.predictions import RISK_TASKS, ModelRisks
from hf_followup.repositories.bundle import digest
from hf_followup.repositories.predictions import file_hash, resolve_bundle


def baseline_facts(facts: dict) -> dict:
    """Require all baseline predictors and reject time, outcomes, missing/invalid inputs."""
    if not isinstance(facts, dict):
        raise ValueError("Patient facts must be a baseline-feature dictionary")
    if set(facts) != set(FEATURES):
        raise ValueError(
            f"Expected exactly baseline features; missing={sorted(set(FEATURES) - set(facts))}, extra={sorted(set(facts) - set(FEATURES))}"
        )
    cleaned = {}
    for field in FEATURES:
        raw = facts[field]
        if isinstance(raw, np.generic):
            raw = raw.item()  # Dataframe/scalar callers share the JSON-native contract.
        if not isinstance(raw, (int, float, bool)) or not math.isfinite(raw):
            raise ValueError(f"{field} must be a finite numeric value")
        value = float(raw)
        if field in BINARY_FIELDS and value not in (0, 1):
            raise ValueError(f"{field} must be binary 0/1")
        if field == "ejection_fraction" and not 0 <= value <= 100:
            raise ValueError("ejection_fraction must be within 0–100")
        if field in {"age", "serum_creatinine", "serum_sodium"} and value <= 0:
            raise ValueError(f"{field} must be positive")
        if field in {"platelets", "creatinine_phosphokinase"} and value < 0:
            raise ValueError(f"{field} must be nonnegative")
        cleaned[field] = bool(value) if field in BINARY_FIELDS else value
    return cleaned


class RiskPredictor:
    def __init__(self, bundle_root: Path):
        self.directory, self.manifest = resolve_bundle(bundle_root)
        # sklearn persistence requires the training version; do not silently accept drift.
        versions = {
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        }
        for package, actual in versions.items():
            if self.manifest["versions"][package] != actual:
                raise ValueError(
                    f"{package} version mismatch: install {self.manifest['versions'][package]} (loaded {actual})"
                )
        split_path = self.directory / "split_manifest.json"
        if file_hash(split_path) != self.manifest["file_hashes"]["split_manifest.json"]:
            raise ValueError("Split manifest checksum mismatch")
        split = json.loads(split_path.read_text())
        self.development_ids, self.test_ids = set(split["development_ids"]), set(split["test_ids"])
        if (
            self.development_ids & self.test_ids
            or split["source_hash"] != self.manifest["source_hash"]
        ):
            raise ValueError("Invalid frozen train/test lineage")
        self.models = {}
        for task in RISK_TASKS:
            metadata = self.manifest["models"][task]
            # Fixed filenames prevent artifact path traversal. Hash before deserialization.
            path = self.directory / f"{task}_pipeline.joblib"
            if file_hash(path) != metadata["artifact_sha256"]:
                raise ValueError(f"Artifact checksum mismatch: {task}")
            pipeline = joblib.load(path)
            expected_class = {
                "logistic_regression": "LogisticRegression",
                "random_forest": "RandomForestClassifier",
                "gradient_boosting": "GradientBoostingClassifier",
            }[metadata["family"]]
            if type(pipeline.named_steps["model"]).__name__ != expected_class:
                raise ValueError(f"Saved pipeline family differs from selection: {task}")
            if any(
                pipeline.get_params()[name] != value
                for name, value in metadata["best_params"].items()
            ):
                raise ValueError(f"Saved pipeline parameters differ from selection: {task}")
            if list(pipeline.feature_names_in_) != metadata["features"] or list(
                pipeline.classes_
            ) != [0, 1]:
                raise ValueError(f"Saved feature order/classes do not match metadata: {task}")
            self.models[task] = pipeline

    def predict_patient(self, facts: dict) -> dict:
        """New records always have new_patient_inference provenance, even if IDs repeat."""
        return self.predict_many({"new-record": facts})["new-record"]

    def predict_many(
        self, patients: dict[str, dict], *, cohort_source_hash: str | None = None
    ) -> dict:
        """Return JSON-native risk objects; only a verified original cohort gets split tags."""
        if not patients:
            return {}
        if any(not isinstance(pid, str) or not pid for pid in patients):
            raise ValueError("Patient identifiers must be nonempty strings")
        facts = {pid: baseline_facts(row) for pid, row in patients.items()}
        x = pd.DataFrame.from_dict(facts, orient="index").loc[:, list(FEATURES)].astype(float)
        if cohort_source_hash is not None and cohort_source_hash != self.manifest["source_hash"]:
            raise ValueError("Scoring cohort hash does not match the frozen training cohort")
        if cohort_source_hash is not None and set(patients) != self.development_ids | self.test_ids:
            raise ValueError("Original-cohort provenance requires complete frozen patient coverage")
        results = {pid: {"bundle_id": self.manifest["bundle_id"]} for pid in patients}
        for task, pipeline in self.models.items():
            metadata = self.manifest["models"][task]
            fields = metadata["features"]
            frame = x[fields]  # Saved feature order is part of the public artifact contract.
            scores = pipeline.predict_proba(frame)[:, 1]
            if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
                raise ValueError(f"Non-finite/out-of-range model output: {task}")
            linear = metadata["family"] == "logistic_regression"
            if linear:
                transformed = pipeline.named_steps["preprocessor"].transform(frame)
                names = [
                    name.split("__", 1)[1]
                    for name in pipeline.named_steps["preprocessor"].get_feature_names_out()
                ]
                contributions = transformed * pipeline.named_steps["model"].coef_[0]
                intercept = float(pipeline.named_steps["model"].intercept_[0])
                # Verify that displayed feature contributions reconstruct the actual model.
                np.testing.assert_allclose(
                    contributions.sum(axis=1) + intercept,
                    pipeline.decision_function(frame),
                    atol=1e-10,
                )
            else:
                names, intercept = fields, None
            for i, pid in enumerate(x.index):
                provenance = "new_patient_inference"
                if cohort_source_hash is not None:
                    provenance = (
                        "held_out_test" if pid in self.test_ids else "development_in_sample"
                    )
                score = float(scores[i])
                lower, upper = (
                    metadata["band_cutoffs"]["lower_max"],
                    metadata["band_cutoffs"]["middle_max"],
                )
                evidence = [
                    {
                        "id": f"{task}_{field}",
                        "field": field,
                        "value": facts[pid][field],
                        "unit": UNITS.get(field),
                        "predicate": f"recorded {field.replace('_', ' ')}",
                        "scale": "log_odds" if linear else "recorded_measurement",
                        "contribution": float(contributions[i, j]) if linear else None,
                    }
                    for j, field in enumerate(names)
                ]
                results[pid][task] = {
                    "score": score,
                    "band": "lower" if score <= lower else "middle" if score <= upper else "higher",
                    "classification_positive": score >= metadata["classification_threshold"],
                    "classification_threshold": metadata["classification_threshold"],
                    "model_family": metadata["family"],
                    "model_version": metadata["model_version"],
                    "score_kind": "model_output",
                    "calibration_status": "not_calibrated",
                    "prediction_provenance": provenance,
                    "explanation_method": metadata["explanation_method"],
                    "evidence": evidence,
                    "intercept": intercept,
                }
        return {
            pid: ModelRisks.model_validate(risks).model_dump() for pid, risks in results.items()
        }

    def cache_payload(self, cohort) -> dict:
        facts = {pid: row["facts"] for pid, row in cohort.features.items()}
        predictions = self.predict_many(facts, cohort_source_hash=cohort.manifest["source_hash"])
        return {
            "bundle_id": self.manifest["bundle_id"],
            "patients": {
                pid: {"features_digest": digest(baseline_facts(facts[pid])), "risks": risks}
                for pid, risks in predictions.items()
            },
        }
