"""Tests for the SQLite local cache/outbox repository.

Covers: cohort round-trip, predictions, reports, command idempotency,
revision conflicts, pending-sync tracking, summary cache, and restart durability.
"""

import json

import pytest

from hf_followup.domain.errors import DomainError
from hf_followup.repositories.sqlite import SQLiteRepository


@pytest.fixture()
def repo(tmp_path):
    """Fresh SQLite repo in a temporary directory."""
    return SQLiteRepository(tmp_path / "test.db")


@pytest.fixture()
def sample_cohort():
    """Minimal cohort data matching the expected schema."""
    features = {
        "HF-0001": {
            "patient_id": "HF-0001",
            "source_row": 1,
            "facts": {"age": 75.0, "ejection_fraction": 20.0, "serum_creatinine": 1.9},
        },
        "HF-0002": {
            "patient_id": "HF-0002",
            "source_row": 2,
            "facts": {"age": 60.0, "ejection_fraction": 45.0, "serum_creatinine": 1.0},
        },
    }
    manifest = {
        "cohort_id": "test-cohort",
        "source_hash": "abc123",
        "accepted_count": 2,
        "feature_allowlist": ["age", "ejection_fraction", "serum_creatinine"],
    }
    return manifest, features


# ------------------------------------------------------------------
# Cohort round-trip
# ------------------------------------------------------------------


class TestCohortStorage:
    def test_store_and_load(self, repo, sample_cohort):
        manifest, features = sample_cohort
        repo.store_cohort("test-cohort", "abc123", manifest, features)
        result = repo.load_cohort("test-cohort")
        assert result["manifest"]["cohort_id"] == "test-cohort"
        assert result["manifest"]["accepted_count"] == 2
        assert set(result["features"]) == {"HF-0001", "HF-0002"}
        assert result["features"]["HF-0001"]["facts"]["age"] == 75.0

    def test_load_missing_raises(self, repo):
        with pytest.raises(DomainError, match="not stored"):
            repo.load_cohort("nonexistent")

    def test_store_is_idempotent(self, repo, sample_cohort):
        manifest, features = sample_cohort
        repo.store_cohort("test-cohort", "abc123", manifest, features)
        repo.store_cohort("test-cohort", "abc123", manifest, features)
        result = repo.load_cohort("test-cohort")
        assert result["manifest"]["accepted_count"] == 2

    def test_features_ordered_by_source_row(self, repo, sample_cohort):
        manifest, features = sample_cohort
        repo.store_cohort("test-cohort", "abc123", manifest, features)
        result = repo.load_cohort("test-cohort")
        ids = list(result["features"])
        assert ids == ["HF-0001", "HF-0002"]


# ------------------------------------------------------------------
# Predictions
# ------------------------------------------------------------------


class TestPredictions:
    def test_store_and_load(self, repo):
        patients = {
            "HF-0001": {"score": 0.85, "evidence": [], "prediction_provenance": "dev"},
            "HF-0002": {"score": 0.42, "evidence": [], "prediction_provenance": "dev"},
        }
        metadata = {"explanation_method": "shap", "model_id": "logreg_v1"}
        repo.store_predictions("c1", "logreg_v1", "v1.0", patients, metadata)
        result = repo.load_predictions("c1", "v1.0")
        assert "logreg_v1" in result
        assert result["logreg_v1"]["patients"]["HF-0001"]["score"] == 0.85
        assert result["logreg_v1"]["explanation_method"] == "shap"

    def test_load_missing_raises(self, repo):
        with pytest.raises(DomainError, match="No predictions"):
            repo.load_predictions("c1", "nonexistent")


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------


class TestReports:
    def test_store_and_load(self, repo):
        report = {"captured_outcomes": 21, "method": "points_v1"}
        repo.store_report("c1", "rpt-1", "cv_fold", report)
        result = repo.load_reports("c1")
        assert "rpt-1" in result
        assert result["rpt-1"]["report_kind"] == "cv_fold"
        assert result["rpt-1"]["captured_outcomes"] == 21

    def test_empty_reports(self, repo):
        assert repo.load_reports("c1") == {}


# ------------------------------------------------------------------
# Command / event protocol
# ------------------------------------------------------------------


class TestCommandProtocol:
    def test_append_first_command(self, repo):
        result = repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "create_snapshot", "method_id": "points_v1"},
        })
        assert result["revision"] == 1
        assert result["sync_status"] == "pending_sync"
        assert result["duplicate"] is False

    def test_sequential_commands(self, repo):
        repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        result = repo.append_command({
            "command_id": "cmd-2",
            "session_id": "s1",
            "expected_revision": 1,
            "payload": {"action": "workflow"},
        })
        assert result["revision"] == 2

    def test_idempotent_duplicate(self, repo):
        cmd = {
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        }
        first = repo.append_command(cmd)
        second = repo.append_command(cmd)
        assert second["duplicate"] is True
        assert second["revision"] == first["revision"]

    def test_conflicting_duplicate_rejected(self, repo):
        repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        with pytest.raises(DomainError, match="different payload"):
            repo.append_command({
                "command_id": "cmd-1",
                "session_id": "s1",
                "expected_revision": 0,
                "payload": {"action": "something_else"},
            })

    def test_stale_revision_rejected(self, repo):
        repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        with pytest.raises(DomainError, match="Expected revision 0 but current is 1"):
            repo.append_command({
                "command_id": "cmd-2",
                "session_id": "s1",
                "expected_revision": 0,
                "payload": {"action": "workflow"},
            })

    def test_read_session_events_ordered(self, repo):
        for i in range(3):
            repo.append_command({
                "command_id": f"cmd-{i}",
                "session_id": "s1",
                "expected_revision": i,
                "payload": {"step": i},
            })
        events = repo.read_session_events("s1")
        assert len(events) == 3
        assert [e["revision"] for e in events] == [1, 2, 3]
        assert [e["payload"]["step"] for e in events] == [0, 1, 2]

    def test_sessions_are_isolated(self, repo):
        repo.append_command({
            "command_id": "cmd-a",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"session": "s1"},
        })
        repo.append_command({
            "command_id": "cmd-b",
            "session_id": "s2",
            "expected_revision": 0,
            "payload": {"session": "s2"},
        })
        assert len(repo.read_session_events("s1")) == 1
        assert len(repo.read_session_events("s2")) == 1

    def test_pending_commands_and_mark_synced(self, repo):
        repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        pending = repo.pending_commands("s1")
        assert len(pending) == 1
        assert pending[0]["command_id"] == "cmd-1"

        repo.mark_synced("cmd-1")
        assert repo.pending_commands("s1") == []

    def test_mark_synced_missing_raises(self, repo):
        with pytest.raises(DomainError, match="not found or already synced"):
            repo.mark_synced("nonexistent")

    def test_mark_synced_twice_raises(self, repo):
        repo.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        repo.mark_synced("cmd-1")
        with pytest.raises(DomainError, match="not found or already synced"):
            repo.mark_synced("cmd-1")


# ------------------------------------------------------------------
# Summary cache
# ------------------------------------------------------------------


class TestSummaryCache:
    def test_write_and_read(self, repo):
        summary = {
            "patient_id": "HF-0001",
            "evidence_digest": "abc",
            "text": "Patient has elevated creatinine.",
            "status": "cached",
        }
        repo.write_summary("key-1", summary)
        result = repo.read_summary("key-1")
        assert result["text"] == "Patient has elevated creatinine."
        assert result["patient_id"] == "HF-0001"

    def test_read_missing_returns_none(self, repo):
        assert repo.read_summary("nonexistent") is None

    def test_overwrite_updates(self, repo):
        repo.write_summary("key-1", {"patient_id": "HF-0001", "evidence_digest": "a", "v": 1})
        repo.write_summary("key-1", {"patient_id": "HF-0001", "evidence_digest": "a", "v": 2})
        assert repo.read_summary("key-1")["v"] == 2


# ------------------------------------------------------------------
# Durability: survives close + reopen
# ------------------------------------------------------------------


class TestDurability:
    def test_survives_restart(self, tmp_path, sample_cohort):
        db_path = tmp_path / "durable.db"
        manifest, features = sample_cohort

        # Session 1: store data and append a command.
        repo1 = SQLiteRepository(db_path)
        repo1.store_cohort("test-cohort", "abc123", manifest, features)
        repo1.append_command({
            "command_id": "cmd-1",
            "session_id": "s1",
            "expected_revision": 0,
            "payload": {"action": "snapshot"},
        })
        repo1.write_summary("sk-1", {
            "patient_id": "HF-0001",
            "evidence_digest": "d1",
            "text": "summary text",
        })
        repo1.close()

        # Session 2: reopen and verify everything is still there.
        repo2 = SQLiteRepository(db_path)
        cohort = repo2.load_cohort("test-cohort")
        assert cohort["manifest"]["accepted_count"] == 2
        assert set(cohort["features"]) == {"HF-0001", "HF-0002"}

        events = repo2.read_session_events("s1")
        assert len(events) == 1
        assert events[0]["command_id"] == "cmd-1"
        assert events[0]["revision"] == 1

        summary = repo2.read_summary("sk-1")
        assert summary["text"] == "summary text"

        # Can continue appending after restart.
        result = repo2.append_command({
            "command_id": "cmd-2",
            "session_id": "s1",
            "expected_revision": 1,
            "payload": {"action": "workflow"},
        })
        assert result["revision"] == 2
        repo2.close()
