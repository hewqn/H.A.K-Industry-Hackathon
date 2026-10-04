"""Promote a completed experiment to an immutable, versioned inference/read bundle.

No new model choice or parameter search happens here. The exact three selected
pipelines, thresholds and band cutoffs are copied and validated before activation.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import joblib

from hf_followup.domain.predictions import RISK_TASKS
from hf_followup.ml.inference import RiskPredictor
from hf_followup.repositories.bundle import digest
from hf_followup.repositories.predictions import BUNDLE_SCHEMA, file_hash, load_prediction_bundle


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def publish_experiment(experiment_dir: Path, output_root: Path, cohort) -> Path:
    """Publish locally; returns the immutable bundle path and activates current.json."""
    report = json.loads((experiment_dir / "experiment_report.json").read_text())
    split = json.loads((experiment_dir / "split_manifest.json").read_text())
    if (
        report["source_hash"] != cohort.manifest["source_hash"]
        or split["source_hash"] != report["source_hash"]
    ):
        raise ValueError("Experiment source hash differs from the scoring cohort")
    if set(report["tasks"]) != set(RISK_TASKS) or report["split"] != split:
        raise ValueError("Experiment has missing outputs or inconsistent split lineage")
    models = {}
    for task in RISK_TASKS:
        task_report = report["tasks"][task]
        family = task_report["selected_family"]
        selected_report = task_report["models"][family]
        threshold = task_report["selected_threshold"]
        lower, upper = (task_report["band_cutoffs"][name] for name in ("lower_max", "middle_max"))
        if not 0 <= threshold <= 1 or not 0 <= lower <= upper <= 1:
            raise ValueError(f"Invalid frozen threshold/bands: {task}")
        if threshold != selected_report["development_threshold"]:
            raise ValueError(f"Selected threshold differs from the chosen model: {task}")
        models[task] = {
            "family": family,
            "features": task_report["features"],
            "classification_threshold": threshold,
            "band_cutoffs": task_report["band_cutoffs"],
            "threshold_policy": selected_report["threshold_policy"],
            "band_policy": task_report["band_policy"],
            "best_params": selected_report["best_params"],
            "score_kind": "model_output",
            "calibration_status": "not_calibrated",
            "explanation_method": "linear_log_odds"
            if family == "logistic_regression"
            else "recorded_features_no_local_attribution",
            "artifact_sha256": file_hash(experiment_dir / f"{task}_pipeline.joblib"),
        }
    # Content-derived ID avoids silently replacing a model version when settings change.
    identity = {
        "publication_format": "app-and-delta-v1",
        "source_hash": report["source_hash"],
        "models": models,
        "split_sha256": file_hash(experiment_dir / "split_manifest.json"),
        "report_sha256": file_hash(experiment_dir / "experiment_report.json"),
    }
    bundle_id = "hf-" + digest(identity)[:20]
    for task, metadata in models.items():
        metadata["model_version"] = f"{bundle_id}/{task}"
    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "publication_format": "app-and-delta-v1",
        "bundle_id": bundle_id,
        "cohort_id": cohort.manifest["cohort_id"],
        "source_hash": report["source_hash"],
        "feature_group_version": report["feature_group_version"],
        "target": "recorded_death_during_observed_follow_up",
        "selection_policy": report["selection_policy"],
        "selection": report["selection"],
        "versions": {
            **report["versions"],
            "joblib": report["versions"].get("joblib", joblib.__version__),
        },
        "models": models,
        "limitations": report["limitations"],
        "file_hashes": {},
    }
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=output_root) as folder:
        staging = Path(folder)
        for task in RISK_TASKS:
            shutil.copyfile(
                experiment_dir / f"{task}_pipeline.joblib", staging / f"{task}_pipeline.joblib"
            )
        for source, target in (
            ("split_manifest.json", "split_manifest.json"),
            ("experiment_report.json", "evaluation_report.json"),
        ):
            shutil.copyfile(experiment_dir / source, staging / target)
            manifest["file_hashes"][target] = file_hash(staging / target)
        write_json(staging / "model_metadata.json", manifest)
        predictor = RiskPredictor(staging)
        payload = predictor.cache_payload(cohort)
        # Save the actual logistic intercept for the ranking/explanation adapter.
        first = next(iter(payload["patients"].values()))["risks"]
        for task in RISK_TASKS:
            models[task]["intercept"] = first[task]["intercept"]
        write_json(staging / "predictions.json", payload)
        manifest["file_hashes"]["predictions.json"] = file_hash(staging / "predictions.json")
        # Exact columns of databricks/sql/001_tables.sql; no individual target labels.
        # Spark can read this on a permitted Volume; the app uses predictions.json.
        delta_path = staging / "delta_predictions.jsonl"
        with delta_path.open("w") as handle:
            for pid, patient in payload["patients"].items():
                for task in RISK_TASKS:
                    risk = patient["risks"][task]
                    row = {
                        "cohort_id": manifest["cohort_id"],
                        "model_id": task,
                        "patient_id": pid,
                        "model_version": risk["model_version"],
                        "score": risk["score"],
                        "prediction_json": json.dumps(
                            {
                                "bundle_id": bundle_id,
                                "features_digest": patient["features_digest"],
                                "risk": risk,
                            },
                            allow_nan=False,
                        ),
                        "model_metadata_json": json.dumps(
                            {
                                **models[task],
                                "source_hash": manifest["source_hash"],
                                "bundle_id": bundle_id,
                            },
                            allow_nan=False,
                        ),
                    }
                    handle.write(json.dumps(row, allow_nan=False) + "\n")
        manifest["file_hashes"]["delta_predictions.jsonl"] = file_hash(delta_path)
        write_json(staging / "model_metadata.json", manifest)
        load_prediction_bundle(staging, cohort)  # Validate the API boundary before activation.
        final = output_root / bundle_id
        if final.exists():
            if file_hash(final / "model_metadata.json") != file_hash(
                staging / "model_metadata.json"
            ):
                raise ValueError("An immutable bundle ID already exists with different contents")
            load_prediction_bundle(final, cohort)
        else:
            # Rename a complete directory: readers cannot observe a half-published cache.
            os.rename(staging, final)
        pointer = {
            "bundle_id": bundle_id,
            "metadata_sha256": file_hash(final / "model_metadata.json"),
        }
        with tempfile.NamedTemporaryFile(
            mode="w", dir=output_root, prefix=".current-", delete=False
        ) as handle:
            json.dump(pointer, handle, indent=2)
            handle.write("\n")
            temporary_pointer = Path(handle.name)
        os.replace(temporary_pointer, output_root / "current.json")
    return final
