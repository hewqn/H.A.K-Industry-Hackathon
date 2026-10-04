"""Load a checksummed frozen read cache; no sklearn, joblib, fitting or cloud calls.

The database owner can return this same envelope from Delta/export transport.
Checksums detect corruption, not authorship: only use trusted team-created bundles.
Publication changes current.json atomically; an API restart loads the new version.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from hf_followup.domain.constants import FEATURES
from hf_followup.domain.errors import DomainError
from hf_followup.domain.predictions import RISK_TASKS, ModelRisks
from hf_followup.repositories.bundle import digest

BUNDLE_SCHEMA = "risk-model-bundle-v1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_bundle(root: Path) -> tuple[Path, dict]:
    """Accept an immutable bundle directory or the publication root/current pointer."""
    if (root / "current.json").is_file():
        pointer = json.loads((root / "current.json").read_text())
        bundle_id = pointer["bundle_id"]
        if not re.fullmatch(r"hf-[0-9a-f]{20}", bundle_id):
            raise ValueError("Invalid model bundle ID")
        directory = root / bundle_id
        if file_hash(directory / "model_metadata.json") != pointer["metadata_sha256"]:
            raise ValueError("Model metadata checksum mismatch")
    else:
        directory = root
    manifest = json.loads((directory / "model_metadata.json").read_text())
    if (root / "current.json").is_file() and manifest["bundle_id"] != bundle_id:
        raise ValueError("Current pointer and model bundle IDs differ")
    if manifest["schema_version"] != BUNDLE_SCHEMA:
        raise ValueError("Unsupported model bundle schema")
    if not re.fullmatch(r"hf-[0-9a-f]{20}", manifest["bundle_id"]):
        raise ValueError("Invalid model bundle ID")
    if set(manifest["models"]) != set(RISK_TASKS):
        raise ValueError("Bundle must contain exactly three risk models")
    return directory, manifest


@dataclass(frozen=True)
class PredictionBundle:
    manifest: dict
    patients: dict
    report: dict
    # Resolve the publication pointer once, keeping lazy inference on this version.
    directory: Path

    def ranking_predictions(self) -> dict:
        """Adapt the shared risk objects to the existing deterministic ranking engine."""
        return {
            task: {
                **self.manifest["models"][task],
                "patients": {pid: row["risks"][task] for pid, row in self.patients.items()},
            }
            for task in RISK_TASKS
        }


def load_prediction_bundle(root: Path | None, cohort) -> PredictionBundle | None:
    """Fail closed on corrupt/stale publication; no publication means points-only mode."""
    if root is None or not root.exists():
        return None
    if not (root / "current.json").exists() and not (root / "model_metadata.json").exists():
        return None
    try:
        directory, manifest = resolve_bundle(root)
        if (
            manifest["source_hash"] != cohort.manifest["source_hash"]
            or manifest["cohort_id"] != cohort.manifest["cohort_id"]
        ):
            raise ValueError("Model bundle belongs to a different cohort")
        for name in ("predictions.json", "evaluation_report.json", "split_manifest.json"):
            if file_hash(directory / name) != manifest["file_hashes"][name]:
                raise ValueError(f"Checksum mismatch: {name}")
        payload = json.loads((directory / "predictions.json").read_text())
        if payload["bundle_id"] != manifest["bundle_id"] or set(payload["patients"]) != set(
            cohort.features
        ):
            raise ValueError("Prediction coverage/bundle does not match the cohort")
        for pid, row in payload["patients"].items():
            facts = {field: cohort.features[pid]["facts"][field] for field in FEATURES}
            if row["features_digest"] != digest(facts):
                raise ValueError(f"Prediction features changed for {pid}")
            risks = ModelRisks.model_validate(row["risks"]).model_dump()
            if risks["bundle_id"] != manifest["bundle_id"]:
                raise ValueError("Patient risk bundle mismatch")
            for task in RISK_TASKS:
                estimate, metadata = risks[task], manifest["models"][task]
                if (
                    estimate["model_version"] != metadata["model_version"]
                    or estimate["model_family"] != metadata["family"]
                    or estimate["classification_threshold"] != metadata["classification_threshold"]
                ):
                    raise ValueError("Prediction model/threshold mismatch")
                if estimate["classification_positive"] != (
                    estimate["score"] >= estimate["classification_threshold"]
                ):
                    raise ValueError("Classifier output does not apply the saved threshold")
                lower, upper = (
                    metadata["band_cutoffs"]["lower_max"],
                    metadata["band_cutoffs"]["middle_max"],
                )
                expected_band = (
                    "lower"
                    if estimate["score"] <= lower
                    else "middle"
                    if estimate["score"] <= upper
                    else "higher"
                )
                if estimate["band"] != expected_band:
                    raise ValueError("Relative band does not apply the saved boundaries")
            row["risks"] = risks
        report = json.loads((directory / "evaluation_report.json").read_text())
        return PredictionBundle(manifest, payload["patients"], report, directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DomainError(
            "model_bundle_invalid", f"Frozen ML cache could not be loaded: {exc}", 503
        ) from exc
