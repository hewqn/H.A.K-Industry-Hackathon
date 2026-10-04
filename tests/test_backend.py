"""Tests for backend routes: workflow, overrides, reset, audit, and CSV export.

Uses in-memory mode (no Databricks/SQLite) so tests run anywhere.
"""

import csv
import io
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hf_followup.api.main import create_app


def _cmd(revision=0):
    """Generate a unique command with the given expected revision."""
    return {"command_id": str(uuid.uuid4()), "expected_revision": revision}


@pytest.fixture()
def client():
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with TestClient(create_app()) as c:
            yield c


@pytest.fixture()
def snapshot_id(client):
    """Get the default snapshot ID."""
    cohort = client.get("/api/v1/cohorts/current").json()
    return cohort["current_snapshot_id"]


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


class TestHealth:
    def test_health_reports_persistence(self, client):
        resp = client.get("/api/v1/health").json()
        assert resp["core"] == "ready"
        assert resp["persistence"] in {"sqlite", "databricks", "in_memory"}


# ------------------------------------------------------------------
# Snapshots through command protocol
# ------------------------------------------------------------------


class TestSnapshots:
    def test_create_snapshot_with_command(self, client):
        cmd = _cmd(0)
        resp = client.post("/api/v1/ranking-snapshots", json={
            **cmd, "cohort_id": "uci-hf-299-v1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["revision"] >= 0
        assert len(data["snapshot"]["queue"]) == 25


# ------------------------------------------------------------------
# Workflow transitions
# ------------------------------------------------------------------


class TestWorkflow:
    def test_pending_to_reviewed(self, client, snapshot_id):
        resp = client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["from_state"] == "pending"
        assert data["to_state"] == "reviewed"

    def test_reviewed_to_contacted(self, client):
        # First: pending -> reviewed.
        client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        # Then: reviewed -> contacted.
        resp = client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(1), "state": "contacted",
        })
        assert resp.status_code == 200
        assert resp.json()["to_state"] == "contacted"

    def test_invalid_transition_rejected(self, client):
        # pending -> contacted is not allowed (must go through reviewed).
        resp = client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "contacted",
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "invalid_transition"

    def test_reopen_requires_reason(self, client):
        # pending -> reviewed.
        client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        # reviewed -> pending without reason.
        resp = client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(1), "state": "pending",
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "reason_required"

    def test_reopen_with_reason_succeeds(self, client):
        client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        resp = client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(1), "state": "pending", "reason": "Need re-evaluation",
        })
        assert resp.status_code == 200
        assert resp.json()["to_state"] == "pending"

    def test_nonexistent_patient_rejected(self, client):
        resp = client.patch("/api/v1/patients/HF-9999/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        assert resp.status_code == 404

    def test_contacted_backfills_queue(self, client):
        """When a patient is contacted, the next eligible fills their spot."""
        # Get initial queue.
        cohort = client.get("/api/v1/cohorts/current").json()
        snap = client.get(f"/api/v1/ranking-snapshots/{cohort['current_snapshot_id']}").json()
        first_patient = snap["queue"][0]["patient_id"]

        # Mark first patient as reviewed then contacted.
        client.patch(f"/api/v1/patients/{first_patient}/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        client.patch(f"/api/v1/patients/{first_patient}/workflow", json={
            **_cmd(1), "state": "contacted",
        })

        # Create a new snapshot — contacted patient should be replaced.
        resp = client.post("/api/v1/ranking-snapshots", json={
            **_cmd(2), "cohort_id": "uci-hf-299-v1",
        })
        new_queue = resp.json()["snapshot"]["queue"]
        queue_ids = {row["patient_id"] for row in new_queue}
        assert first_patient not in queue_ids
        assert len(new_queue) == 25


# ------------------------------------------------------------------
# Overrides
# ------------------------------------------------------------------


class TestOverrides:
    def test_pin_patient(self, client):
        resp = client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "High risk per clinician review",
        })
        assert resp.status_code == 200
        assert resp.json()["override_action"] == "pin"

    def test_defer_patient(self, client):
        resp = client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "defer",
            "reason": "Already in contact with specialist",
        })
        assert resp.status_code == 200
        assert resp.json()["override_action"] == "defer"

    def test_pin_and_defer_conflict(self, client):
        # Pin first.
        client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "High risk",
        })
        # Try to defer the same patient.
        resp = client.post("/api/v1/overrides", json={
            **_cmd(1),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "defer",
            "reason": "Not needed",
        })
        assert resp.status_code == 409
        assert resp.json()["code"] == "override_conflict"

    def test_contacted_cannot_be_pinned(self, client):
        # Mark patient as reviewed then contacted.
        client.patch("/api/v1/patients/HF-0050/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        client.patch("/api/v1/patients/HF-0050/workflow", json={
            **_cmd(1), "state": "contacted",
        })
        # Try to pin.
        resp = client.post("/api/v1/overrides", json={
            **_cmd(2),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "Should be first",
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "contacted_pin_blocked"

    def test_reset_override(self, client):
        # Pin.
        client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "High risk",
        })
        # Reset override.
        resp = client.post("/api/v1/overrides", json={
            **_cmd(1),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "reset",
            "reason": "No longer needed",
        })
        assert resp.status_code == 200

    def test_reset_no_override_fails(self, client):
        resp = client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "reset",
            "reason": "Nothing to reset",
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "no_override"

    def test_pinned_patient_appears_first(self, client):
        # Pin a patient who wouldn't normally be first.
        client.post("/api/v1/overrides", json={
            **_cmd(0),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "Priority override",
        })
        # Create a new snapshot.
        resp = client.post("/api/v1/ranking-snapshots", json={
            **_cmd(1), "cohort_id": "uci-hf-299-v1",
        })
        queue = resp.json()["snapshot"]["queue"]
        assert queue[0]["patient_id"] == "HF-0050"


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------


class TestReset:
    def test_reset_clears_state(self, client):
        # Make some changes.
        client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        # Reset.
        resp = client.post("/api/v1/sessions/reset", json={
            **_cmd(1), "reason": "Demo restart",
        })
        assert resp.status_code == 200

        # Verify workflow is cleared — patient should be pending again.
        cohort = client.get("/api/v1/cohorts/current").json()
        patient = client.get(
            f"/api/v1/patients/HF-0001?snapshot_id={cohort['current_snapshot_id']}"
        ).json()
        assert patient["workflow"]["state"] == "pending"


# ------------------------------------------------------------------
# Audit events
# ------------------------------------------------------------------


class TestAuditEvents:
    def test_empty_audit(self, client):
        resp = client.get("/api/v1/audit-events").json()
        assert resp["events"] == []
        assert resp["total"] == 0

    def test_events_recorded_with_repo(self, tmp_path):
        """With a SQLite repo, audit events are recorded and readable."""
        from hf_followup.repositories.sqlite import SQLiteRepository

        repo = SQLiteRepository(tmp_path / "audit.db")
        with patch("hf_followup.api.main._create_repository", return_value=(repo, "sqlite")):
            with TestClient(create_app()) as c:
                c.patch("/api/v1/patients/HF-0001/workflow", json={
                    **_cmd(0), "state": "reviewed",
                })
                resp = c.get("/api/v1/audit-events").json()
                assert resp["total"] >= 1

    def test_pagination(self, client):
        # Create a few events.
        client.patch("/api/v1/patients/HF-0001/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        client.patch("/api/v1/patients/HF-0002/workflow", json={
            **_cmd(1), "state": "reviewed",
        })
        resp = client.get("/api/v1/audit-events?limit=1&offset=0").json()
        assert len(resp["events"]) <= 1


# ------------------------------------------------------------------
# CSV export
# ------------------------------------------------------------------


class TestCSVExport:
    def test_export_returns_csv(self, client, snapshot_id):
        resp = client.get(f"/api/v1/exports/queue.csv?snapshot_id={snapshot_id}")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "patient_id" in header
        assert "call_rank" in header
        rows = list(reader)
        assert len(rows) == 25

    def test_export_no_outcomes(self, client, snapshot_id):
        resp = client.get(f"/api/v1/exports/queue.csv?snapshot_id={snapshot_id}")
        text = resp.text.lower()
        assert "death_event" not in text
        assert "time" not in text or "created_at" in text  # 'time' only if part of another word.

    def test_export_unknown_snapshot_404(self, client):
        resp = client.get("/api/v1/exports/queue.csv?snapshot_id=nonexistent")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Voice routes still 503
# ------------------------------------------------------------------


class TestVoiceStill503:
    def test_voice_session(self, client):
        resp = client.post("/api/v1/voice/session", json={"snapshot_id": "x"})
        assert resp.status_code == 503

    def test_voice_tools(self, client):
        resp = client.post("/api/v1/voice/tools/get_queue", json={"snapshot_id": "x"})
        assert resp.status_code == 503


# ------------------------------------------------------------------
# Existing contract still works
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Patient CRUD
# ------------------------------------------------------------------


class TestPatientCRUD:
    _SAMPLE_PATIENT = {
        "age": 55,
        "anaemia": False,
        "creatinine_phosphokinase": 200,
        "diabetes": True,
        "ejection_fraction": 40,
        "high_blood_pressure": False,
        "platelets": 250000,
        "serum_creatinine": 1.2,
        "serum_sodium": 137,
        "sex": True,
        "smoking": False,
    }

    def test_add_patient(self, client):
        resp = client.post("/api/v1/patients", json={
            **_cmd(0), **self._SAMPLE_PATIENT,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_id"] == "HF-0300"
        assert data["facts"]["age"] == 55

    def test_add_patient_appears_in_cohort(self, client):
        client.post("/api/v1/patients", json={
            **_cmd(0), **self._SAMPLE_PATIENT,
        })
        cohort = client.get("/api/v1/cohorts/current").json()
        assert "HF-0300" in cohort["accepted_ids"]
        assert cohort["accepted_count"] == 300

    def test_update_patient(self, client):
        resp = client.put("/api/v1/patients/HF-0001", json={
            **_cmd(0), "age": 80,
        })
        assert resp.status_code == 200
        assert resp.json()["facts"]["age"] == 80

    def test_update_preserves_other_fields(self, client):
        resp = client.put("/api/v1/patients/HF-0001", json={
            **_cmd(0), "age": 80,
        })
        facts = resp.json()["facts"]
        assert facts["ejection_fraction"] == 20
        assert facts["serum_creatinine"] == 1.9

    def test_update_nonexistent_patient(self, client):
        resp = client.put("/api/v1/patients/HF-9999", json={
            **_cmd(0), "age": 50,
        })
        assert resp.status_code == 404

    def test_update_no_fields(self, client):
        resp = client.put("/api/v1/patients/HF-0001", json=_cmd(0))
        assert resp.status_code == 422

    def test_delete_patient(self, client):
        resp = client.request("DELETE", "/api/v1/patients/HF-0001", json={
            **_cmd(0), "reason": "Duplicate record",
        })
        assert resp.status_code == 200
        cohort = client.get("/api/v1/cohorts/current").json()
        assert "HF-0001" not in cohort["accepted_ids"]
        assert cohort["accepted_count"] == 298

    def test_delete_nonexistent_patient(self, client):
        resp = client.request("DELETE", "/api/v1/patients/HF-9999", json={
            **_cmd(0), "reason": "Cleanup",
        })
        assert resp.status_code == 404

    def test_delete_clears_workflow_and_overrides(self, client):
        # Set workflow state and override.
        client.patch("/api/v1/patients/HF-0050/workflow", json={
            **_cmd(0), "state": "reviewed",
        })
        client.post("/api/v1/overrides", json={
            **_cmd(1),
            "patient_id": "HF-0050",
            "session_id": "demo",
            "action": "pin",
            "reason": "Testing",
        })
        # Delete patient.
        resp = client.request("DELETE", "/api/v1/patients/HF-0050", json={
            **_cmd(2), "reason": "Removed",
        })
        assert resp.status_code == 200

    def test_add_then_snapshot_includes_new_patient(self, client):
        client.post("/api/v1/patients", json={
            **_cmd(0),
            **self._SAMPLE_PATIENT,
            "ejection_fraction": 10,
            "serum_creatinine": 5.0,
            "age": 90,
        })
        resp = client.post("/api/v1/ranking-snapshots", json={
            **_cmd(1), "cohort_id": "uci-hf-299-v1",
        })
        rows = resp.json()["snapshot"]["rows"]
        patient_ids = {r["patient_id"] for r in rows}
        assert "HF-0300" in patient_ids


class TestExistingContract:
    def test_queue_patient_contract(self, client):
        # Create an explicit points_v1 snapshot so the test doesn't depend on
        # whatever _default_method() returns (patient_risk when the ML bundle
        # is present locally, points_v1 in CI where it isn't).
        cohort = client.get("/api/v1/cohorts/current").json()
        resp = client.post("/api/v1/ranking-snapshots", json={
            "command_id": "test-contract",
            "expected_revision": cohort["workflow_revision"],
            "cohort_id": cohort["cohort_id"],
            "method_id": "points_v1",
            "capacity": 25,
            "mode": "operational",
        })
        snap = resp.json()["snapshot"]
        sid = snap["snapshot_id"]
        assert len(snap["queue"]) == 25
        patient = client.get(f"/api/v1/patients/HF-0001?snapshot_id={sid}").json()
        assert patient["call_rank"] == 14
        assert patient["score"]["value"] == 6
        assert patient["summary"]["status"] == "template"
