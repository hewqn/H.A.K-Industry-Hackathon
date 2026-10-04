"""Frozen inference, publication and API boundaries using the real public dataset."""

import json
import math
import shutil
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hf_followup.api.main import create_app
from hf_followup.config import ROOT, Settings
from hf_followup.domain.errors import DomainError
from hf_followup.domain.predictions import RISK_TASKS
from hf_followup.ml.inference import RiskPredictor
from hf_followup.ml.publishing import publish_experiment
from hf_followup.ml.training import train_frozen_selection
from hf_followup.repositories.predictions import load_prediction_bundle


@pytest.fixture(scope="module")
def frozen_models(tmp_path_factory, ingested):
    folder = tmp_path_factory.mktemp("frozen-models")
    selection = json.loads((ROOT / "configs/ml_selection.json").read_text())
    train_frozen_selection(ingested, selection, folder / "training")
    directory = publish_experiment(folder / "training", folder / "published", ingested.cohort)
    return folder, directory, selection


def test_frozen_families_thresholds_evidence_and_new_patient_provenance(frozen_models, ingested):
    folder, directory, selection = frozen_models
    predictor = RiskPredictor(folder / "published")
    bundle = load_prediction_bundle(folder / "published", ingested.cohort)
    assert len(bundle.patients) == 299
    delta_rows = [
        json.loads(line)
        for line in (directory / "delta_predictions.jsonl").read_text().splitlines()
    ]
    assert len(delta_rows) == 897
    assert {row["model_id"] for row in delta_rows} == set(RISK_TASKS)
    assert all(
        set(row)
        == {
            "cohort_id",
            "model_id",
            "patient_id",
            "model_version",
            "score",
            "prediction_json",
            "model_metadata_json",
        }
        for row in delta_rows
    )
    assert set(bundle.ranking_predictions()) == set(RISK_TASKS)
    facts = ingested.cohort.features["HF-0001"]["facts"]
    # Reused IDs do not claim held-out lineage when scoring new/arbitrary inputs.
    new = predictor.predict_many({"HF-0001": facts})["HF-0001"]
    for task in RISK_TASKS:
        estimate = new[task]
        assert estimate["model_family"] == selection["models"][task]["family"]
        assert (
            estimate["classification_threshold"]
            == selection["models"][task]["classification_threshold"]
        )
        assert estimate["classification_positive"] == (
            estimate["score"] >= estimate["classification_threshold"]
        )
        assert estimate["prediction_provenance"] == "new_patient_inference"
        if task != "patient_risk":
            assert all(item["contribution"] is None for item in estimate["evidence"])
    patient = new["patient_risk"]
    log_odds = patient["intercept"] + sum(item["contribution"] for item in patient["evidence"])
    assert patient["score"] == pytest.approx(1 / (1 + math.exp(-log_odds)), abs=1e-12)
    # Repeated publication is idempotent and does not replace the immutable directory.
    assert (
        publish_experiment(folder / "training", folder / "published", ingested.cohort) == directory
    )


@pytest.mark.parametrize(
    "change",
    [
        {"DEATH_EVENT": 1},
        {"time": 10},
        {"ejection_fraction": None},
        {"age": float("nan")},
        {"diabetes": 2},
        {"serum_creatinine": 0},
    ],
)
def test_inference_rejects_labels_and_invalid_baseline_inputs(frozen_models, ingested, change):
    _, directory, _ = frozen_models
    predictor = RiskPredictor(directory)
    facts = {**ingested.cohort.features["HF-0001"]["facts"], **change}
    with pytest.raises(ValueError):
        predictor.predict_patient(facts)


def test_corrupted_artifacts_and_read_cache_fail_closed(frozen_models, ingested, tmp_path):
    _, directory, _ = frozen_models
    copied = tmp_path / "copy"
    shutil.copytree(directory, copied)
    (copied / "heart_risk_pipeline.joblib").write_bytes(b"not a trusted model")
    with pytest.raises(ValueError, match="Artifact checksum"):
        RiskPredictor(copied)
    (copied / "predictions.json").write_text("{}")
    with pytest.raises(DomainError, match="Checksum mismatch"):
        load_prediction_bundle(copied, ingested.cohort)


def test_api_uses_only_cache_and_exposes_all_three_risks(frozen_models, monkeypatch):
    folder, _, selection = frozen_models

    def forbidden_load(*args, **kwargs):
        raise AssertionError("API must never deserialize models or fit during interactions")

    monkeypatch.setattr("joblib.load", forbidden_load)
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published"))) as client:
            cohort = client.get("/api/v1/cohorts/current").json()
            snapshot_id = cohort["current_snapshot_id"]
            snapshot = client.get(f"/api/v1/ranking-snapshots/{snapshot_id}").json()
            assert snapshot["method_id"] == "patient_risk"
            assert len(snapshot["queue"]) == 25
            assert snapshot["queue"][0]["score"]["explanation_method"] == "linear_log_odds"
            response = client.get("/api/v1/patients/HF-0001", params={"snapshot_id": snapshot_id})
            assert response.status_code == 200
            patient = response.json()
            risks_response = client.get(
                "/api/v1/patients/HF-0001/risks", params={"snapshot_id": snapshot_id}
            )
            assert risks_response.status_code == 200
            assert patient["model_risks"] == risks_response.json()
            assert "DEATH_EVENT" not in response.text and '"time"' not in response.text
            assert patient["organs"]["kidney_left"] == patient["organs"]["kidney_right"]
            assert len({item["id"] for item in patient["evidence"]}) == len(patient["evidence"])
            # Voice must see the same published risks as the patient/API contract.
            # Local evidence grants do not contact ElevenLabs or use live credits.
            voice_body = {"snapshot_id": snapshot_id, "patient_id": "HF-0001"}
            grant_response = client.post(
                "/api/v1/voice/context", json=voice_body,
                headers={"Origin": "http://localhost:5173"},
            )
            assert grant_response.status_code == 200
            grant = grant_response.json()
            voice_read = client.post(
                "/api/v1/voice/tools/get_patient",
                json={**voice_body, "cohort_id": grant["cohort_id"]},
                headers={
                    "Origin": "http://localhost:5173",
                    "Authorization": f"Bearer {grant['tool_token']}",
                },
            )
            assert voice_read.status_code == 200
            assert voice_read.json()["risk_outputs_status"] == "ready"
            assert voice_read.json()["patient"]["model_risks"] == patient["model_risks"]
            assert "DEATH_EVENT" not in voice_read.text and '"time"' not in voice_read.text
            models = client.get("/api/v1/models").json()
            assert models["supervised_status"] == "ready"
            for task in RISK_TASKS:
                assert models["selected_models"][task]["family"] == selection["models"][task]["family"]
            alternate = client.post(
                "/api/v1/ranking-snapshots",
                json={
                    "command_id": "ml-snapshot-test",
                    "expected_revision": 0,
                    "method_id": "heart_risk",
                    "capacity": 25,
                },
            )
            assert alternate.status_code == 200
            assert (
                alternate.json()["snapshot"]["queue"][0]["score"]["explanation_method"]
                == "recorded_features_no_local_attribution"
            )
