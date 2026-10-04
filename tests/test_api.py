"""Verify the starter's read contract and live workflow mutation."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from hf_followup.api.main import create_app


def forbidden_keys(value):
    if isinstance(value, dict):
        assert not {"DEATH_EVENT", "time"} & set(value)
        for child in value.values():
            forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            forbidden_keys(child)


def test_queue_patient_contract_and_summary():
    with TestClient(create_app()) as client:
        cohort = client.get("/api/v1/cohorts/current").json()
        snapshot_id = cohort["current_snapshot_id"]
        snapshot = client.get(f"/api/v1/ranking-snapshots/{snapshot_id}").json()
        assert len(snapshot["queue"]) == 25
        response = client.get("/api/v1/patients/HF-0001", params={"snapshot_id": snapshot_id})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"]
        patient = response.json()
        assert patient["call_rank"] == 14
        assert patient["score"]["value"] == 6
        assert patient["organs"]["kidney_left"] == patient["organs"]["kidney_right"]
        assert patient["summary"]["status"] == "template"
        assert len(patient["summary"]["text"].split()) <= 100
        forbidden_keys(patient)
        forbidden_keys(snapshot)


def test_workflow_transition_is_live():
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app()) as client:
            response = client.patch(
                "/api/v1/patients/HF-0001/workflow",
                json={"command_id": "test-command", "expected_revision": 0, "state": "reviewed"},
            )
            assert response.status_code == 200
            assert response.json()["to_state"] == "reviewed"


def test_stale_summary_and_unknown_snapshot():
    with TestClient(create_app()) as client:
        cohort = client.get("/api/v1/cohorts/current").json()
        response = client.post(
            "/api/v1/patients/HF-0001/summary",
            json={"snapshot_id": cohort["current_snapshot_id"], "evidence_digest": "0" * 64},
        )
        assert response.status_code == 409
        assert (
            client.get("/api/v1/patients/HF-0001", params={"snapshot_id": "missing"}).status_code
            == 404
        )
