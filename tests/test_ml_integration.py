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


def test_patient_crud_scores_frozen_models_and_preserves_snapshot_history(frozen_models):
    folder, directory, _ = frozen_models
    predictor = RiskPredictor(directory)
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published"))) as client:
            service = client.app.state.service
            original_id = service.default_snapshot["snapshot_id"]
            original = client.get("/api/v1/patients/HF-0001", params={"snapshot_id": original_id}).json()
            facts = {**original["facts"], "age": 41.0, "ejection_fraction": 60.0, "serum_creatinine": 0.9}
            body = {"command_id": "add-scored-patient", "expected_revision": 0, **facts}
            created = client.post("/api/v1/patients", json=body)
            assert created.status_code == 200
            receipt = created.json()
            assert receipt["patient_id"] == "HF-0300"
            assert receipt["model_risks"] == predictor.predict_patient(facts)
            assert client.post("/api/v1/patients", json=body).json() == receipt
            assert len(service.cohort.features) == 300 and service.revision == 1
            assert client.post("/api/v1/patients", json={**body, "age": 42}).status_code == 409
            before_edit = service.default_snapshot["snapshot_id"]
            for method in RISK_TASKS:
                snapshot = service.create_snapshot(method, 25)
                row = next(row for row in snapshot["rows"] if row["patient_id"] == "HF-0300")
                assert row["score"]["value"] == receipt["model_risks"][method]["score"]
                assert row["model_risks"] == receipt["model_risks"]
                assert row["score"]["intercept"] == receipt["model_risks"][method]["intercept"]
            updated = client.put("/api/v1/patients/HF-0300", json={
                "command_id": "edit-scored-patient", "expected_revision": 1,
                "age": 85, "ejection_fraction": 20, "serum_creatinine": 4,
            })
            assert updated.status_code == 200
            updated_facts = {**facts, "age": 85.0, "ejection_fraction": 20.0, "serum_creatinine": 4.0}
            assert updated.json()["model_risks"] == predictor.predict_patient(updated_facts)
            current_id = service.default_snapshot["snapshot_id"]
            current = client.get("/api/v1/patients/HF-0300", params={"snapshot_id": current_id}).json()
            assert current["facts"] == updated_facts
            assert current["model_risks"] == updated.json()["model_risks"]
            assert client.get("/api/v1/patients/HF-0300", params={"snapshot_id": before_edit}).json()["model_risks"] == receipt["model_risks"]
            # Original patient scores and held-out/development lineage never change.
            assert client.get("/api/v1/patients/HF-0001", params={"snapshot_id": current_id}).json()["model_risks"] == original["model_risks"]
            assert client.get("/api/v1/patients/HF-0300", params={"snapshot_id": original_id}).status_code == 404
            deletion = {"command_id": "delete-scored-patient", "expected_revision": 2, "reason": "Test record"}
            deleted = client.request("DELETE", "/api/v1/patients/HF-0300", json=deletion)
            assert deleted.status_code == 200
            assert client.request("DELETE", "/api/v1/patients/HF-0300", json=deletion).json() == deleted.json()
            for task in RISK_TASKS:
                assert "HF-0300" not in service.predictions[task]["patients"]
                assert all(row["patient_id"] != "HF-0300" for row in service.create_snapshot(task, 25)["rows"])
            next_patient = client.post("/api/v1/patients", json={**body, "command_id": "next-scored-patient", "expected_revision": 3})
            assert next_patient.json()["patient_id"] == "HF-0301"


def test_scored_patient_events_restart_without_deserializing_models(frozen_models, tmp_path):
    from hf_followup.repositories.sqlite import SQLiteRepository

    folder, _, _ = frozen_models
    database = tmp_path / "patients.db"
    settings = Settings(model_bundle_dir=folder / "published", session_id="patient-replay")
    with patch("hf_followup.api.main._create_repository", side_effect=lambda _: (SQLiteRepository(database), "sqlite")):
        with TestClient(create_app(settings)) as client:
            service = client.app.state.service
            facts = service.cohort.features["HF-0001"]["facts"]
            body = {**facts, "command_id": "persist-new-patient", "expected_revision": 0}
            added = client.post("/api/v1/patients", json=body).json()
            edited_body = {"command_id": "persist-edit-patient", "expected_revision": 1, "age": 45}
            edited = client.put("/api/v1/patients/HF-0300", json=edited_body).json()
            deleted_body = {"command_id": "persist-delete-patient", "expected_revision": 2, "reason": "Duplicate baseline"}
            deleted = client.request("DELETE", "/api/v1/patients/HF-0001", json=deleted_body).json()
        with patch("joblib.load", side_effect=AssertionError("Replay must use persisted compatible scores")):
            with TestClient(create_app(settings)) as client:
                service = client.app.state.service
                assert service.revision == 3
                assert "HF-0001" not in service.cohort.features
                row = next(row for row in service.default_snapshot["rows"] if row["patient_id"] == "HF-0300")
                assert row["model_risks"] == edited["model_risks"]
                assert row["facts"]["age"] == 45
                assert client.post("/api/v1/patients", json=body).json() == added
                assert client.put("/api/v1/patients/HF-0300", json=edited_body).json() == edited
                assert client.request("DELETE", "/api/v1/patients/HF-0001", json=deleted_body).json() == deleted


def test_inference_failure_is_atomic_and_stale_revision_does_not_infer(frozen_models):
    folder, _, _ = frozen_models
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published"))) as client:
            service = client.app.state.service
            facts = service.cohort.features["HF-0001"]["facts"]
            service._predictor_factory = lambda: (_ for _ in ()).throw(ValueError("Invalid artifacts"))
            body = {**facts, "command_id": "failed-scoring-command", "expected_revision": 0}
            assert client.post("/api/v1/patients", json={**body, "expected_revision": 10}).status_code == 409
            response = client.post("/api/v1/patients", json=body)
            assert response.status_code == 503 and response.json()["code"] == "inference_unavailable"
            assert service.revision == 0 and len(service.cohort.features) == 299
            assert "failed-scoring-command" not in service._commands
            assert client.put("/api/v1/patients/HF-0001", json={
                "command_id": "failed-scoring-update", "expected_revision": 0, "age": 20,
            }).status_code == 503
            assert service.cohort.features["HF-0001"]["facts"] == facts


def test_legacy_patient_events_are_scored_on_replay(frozen_models, tmp_path):
    from hf_followup.data.ingest import ingest_csv
    from hf_followup.repositories.sqlite import SQLiteRepository

    folder, directory, _ = frozen_models
    repo = SQLiteRepository(tmp_path / "legacy.db")
    facts = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv").cohort.features["HF-0001"]["facts"]
    repo.append_command({
        "command_id": "legacy-unscored-add", "session_id": "legacy", "expected_revision": 0,
        "payload": {"action": "add_patient", "patient_id": "HF-0300", "source_row": 300, "facts": facts},
    })
    with patch("hf_followup.api.main._create_repository", return_value=(repo, "sqlite")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published", session_id="legacy"))) as client:
            row = next(row for row in client.app.state.service.default_snapshot["rows"] if row["patient_id"] == "HF-0300")
            assert row["model_risks"] == RiskPredictor(directory).predict_patient(facts)
            assert row["score"]["prediction_provenance"] == "new_patient_inference"


def test_patient_api_rejects_nonfinite_values_and_outcome_fields():
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings())) as client:
            facts = client.app.state.service.cohort.features["HF-0001"]["facts"]
            body = {**facts, "command_id": "invalid-input-command", "expected_revision": 0}
            for field in ("age", "platelets", "serum_creatinine"):
                response = client.post("/api/v1/patients", content=json.dumps({**body, field: float("inf")}), headers={"Content-Type": "application/json"})
                assert response.status_code == 422
            for field in ("DEATH_EVENT", "time"):
                assert client.post("/api/v1/patients", json={**body, field: 1}).status_code == 422
            assert client.app.state.service.revision == 0


def test_patient_writes_are_serialized_and_do_not_train(frozen_models):
    from concurrent.futures import ThreadPoolExecutor

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    folder, _, _ = frozen_models
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published"))) as client:
            facts = client.app.state.service.cohort.features["HF-0001"]["facts"]
            with patch.object(RandomForestClassifier, "fit", side_effect=AssertionError("No request training")), patch.object(LogisticRegression, "fit", side_effect=AssertionError("No request training")):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    requests = [pool.submit(client.post, "/api/v1/patients", json={
                        **facts, "command_id": f"concurrent-add-{index}", "expected_revision": 0,
                    }) for index in range(2)]
                    assert sorted(request.result().status_code for request in requests) == [200, 409]
            assert client.app.state.service.revision == 1
            assert len(client.app.state.service.cohort.features) == 300


def test_voice_context_is_invalidated_by_crud_and_new_scores_match(frozen_models):
    folder, _, _ = frozen_models
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app(Settings(model_bundle_dir=folder / "published"))) as client:
            client.headers["origin"] = "http://localhost:5173"
            service = client.app.state.service
            old_body = {"snapshot_id": service.default_snapshot["snapshot_id"], "patient_id": "HF-0001"}
            old_grant = client.post("/api/v1/voice/context", json=old_body).json()
            facts = service.cohort.features["HF-0001"]["facts"]
            added = client.post("/api/v1/patients", json={
                **facts, "command_id": "voice-add-patient", "expected_revision": 0,
            }).json()
            stale = client.post("/api/v1/voice/tools/get_patient", json={
                **old_body, "cohort_id": old_grant["cohort_id"],
            }, headers={"Authorization": f"Bearer {old_grant['tool_token']}"})
            assert stale.status_code == 409 and stale.json()["code"] == "stale_voice_context"
            body = {"snapshot_id": service.default_snapshot["snapshot_id"], "patient_id": added["patient_id"]}
            grant = client.post("/api/v1/voice/context", json=body).json()
            read = client.post("/api/v1/voice/tools/get_patient", json={
                **body, "cohort_id": grant["cohort_id"],
            }, headers={"Authorization": f"Bearer {grant['tool_token']}"})
            assert read.status_code == 200
            assert read.json()["patient"]["model_risks"] == added["model_risks"]
            assert "DEATH_EVENT" not in read.text and '"time"' not in read.text
            assert client.request("DELETE", f"/api/v1/patients/{added['patient_id']}", json={
                "command_id": "voice-delete-patient", "expected_revision": 1, "reason": "Test cleanup",
            }).status_code == 200
            assert client.post("/api/v1/voice/tools/get_patient", json={
                **body, "cohort_id": grant["cohort_id"],
            }, headers={"Authorization": f"Bearer {grant['tool_token']}"}).status_code == 409
