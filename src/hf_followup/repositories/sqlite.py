"""SQLite local cache/outbox implementing the Repository protocol.

This is a durable local store that survives restarts. It serves as:
- Primary local persistence when Databricks is unavailable (restricted workspace).
- Offline outbox for commands that will sync to Databricks later.

Every command is checked for duplicate command IDs and expected session revisions
before it is appended. Offline writes are marked ``pending_sync`` and must be
replayed to Databricks in order; replay stops on the first revision conflict.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hf_followup.domain.errors import DomainError
from hf_followup.repositories.bundle import canonical, digest

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS cohort_manifests (
    cohort_id   TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    manifest    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patient_features (
    cohort_id  TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    features   TEXT NOT NULL,
    PRIMARY KEY (cohort_id, patient_id)
);

CREATE TABLE IF NOT EXISTS model_predictions (
    cohort_id     TEXT NOT NULL,
    model_id      TEXT NOT NULL,
    patient_id    TEXT NOT NULL,
    model_version TEXT NOT NULL,
    score         REAL NOT NULL,
    prediction    TEXT NOT NULL,
    metadata      TEXT NOT NULL,
    PRIMARY KEY (cohort_id, model_id, patient_id)
);

CREATE TABLE IF NOT EXISTS evaluation_reports (
    cohort_id   TEXT NOT NULL,
    report_id   TEXT PRIMARY KEY,
    report_kind TEXT NOT NULL,
    report      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_events (
    command_id        TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    revision          INTEGER NOT NULL,
    expected_revision INTEGER NOT NULL,
    command_digest    TEXT NOT NULL,
    payload           TEXT NOT NULL,
    sync_status       TEXT NOT NULL DEFAULT 'pending_sync',
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS summary_cache (
    cache_key       TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    payload         TEXT NOT NULL
);
"""


class SQLiteRepository:
    """Implements ``repositories.base.Repository`` backed by a local SQLite file."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, isolation_level="DEFERRED", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Cohort
    # ------------------------------------------------------------------

    def store_cohort(self, cohort_id: str, source_hash: str, manifest: dict,
                     features: dict[str, dict]) -> None:
        """Persist a validated cohort. Called once at ingest, idempotent on cohort_id."""
        manifest_json = canonical(manifest)
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO cohort_manifests (cohort_id, source_hash, manifest) "
                "VALUES (?, ?, ?)",
                (cohort_id, source_hash, manifest_json),
            )
            for patient_id, record in features.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO patient_features "
                    "(cohort_id, patient_id, source_row, features) VALUES (?, ?, ?, ?)",
                    (cohort_id, patient_id, record["source_row"],
                     canonical(record["facts"])),
                )

    def load_cohort(self, cohort_id: str) -> dict:
        """Return manifest + allowlisted features; never raw outcomes."""
        row = self._conn.execute(
            "SELECT manifest FROM cohort_manifests WHERE cohort_id = ?", (cohort_id,)
        ).fetchone()
        if row is None:
            raise DomainError("cohort_not_found", f"Cohort {cohort_id!r} is not stored.", 404)
        manifest = json.loads(row["manifest"])
        feature_rows = self._conn.execute(
            "SELECT patient_id, source_row, features FROM patient_features "
            "WHERE cohort_id = ? ORDER BY source_row",
            (cohort_id,),
        ).fetchall()
        features = {
            r["patient_id"]: {
                "patient_id": r["patient_id"],
                "source_row": r["source_row"],
                "facts": json.loads(r["features"]),
            }
            for r in feature_rows
        }
        return {"manifest": manifest, "features": features}

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def store_predictions(self, cohort_id: str, model_id: str, model_version: str,
                          patients: dict, metadata: dict) -> None:
        """Persist frozen predictions published by the ML owner."""
        metadata_json = canonical(metadata)
        with self._conn:
            for patient_id, prediction in patients.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO model_predictions "
                    "(cohort_id, model_id, patient_id, model_version, score, prediction, metadata) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cohort_id, model_id, patient_id, model_version,
                     prediction["score"], canonical(prediction), metadata_json),
                )

    def load_predictions(self, cohort_id: str, model_version: str) -> dict:
        """Return complete frozen predictions with model/explanation/provenance metadata."""
        rows = self._conn.execute(
            "SELECT model_id, patient_id, model_version, score, prediction, metadata "
            "FROM model_predictions WHERE cohort_id = ? AND model_version = ?",
            (cohort_id, model_version),
        ).fetchall()
        if not rows:
            raise DomainError(
                "predictions_not_found",
                f"No predictions for cohort {cohort_id!r} version {model_version!r}.",
                404,
            )
        result: dict[str, dict] = {}
        for r in rows:
            model_id = r["model_id"]
            if model_id not in result:
                meta = json.loads(r["metadata"])
                result[model_id] = {
                    "model_id": model_id,
                    "model_version": r["model_version"],
                    "explanation_method": meta.get("explanation_method", "unknown"),
                    "patients": {},
                    **meta,
                }
            result[model_id]["patients"][r["patient_id"]] = json.loads(r["prediction"])
        return result

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def store_report(self, cohort_id: str, report_id: str, report_kind: str,
                     report: dict) -> None:
        """Persist an aggregate report (CV, test, descriptive)."""
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO evaluation_reports "
                "(cohort_id, report_id, report_kind, report) VALUES (?, ?, ?, ?)",
                (cohort_id, report_id, report_kind, canonical(report)),
            )

    def load_reports(self, cohort_id: str) -> dict:
        """Return aggregate descriptive/CV/test reports with their population labels."""
        rows = self._conn.execute(
            "SELECT report_id, report_kind, report FROM evaluation_reports "
            "WHERE cohort_id = ? ORDER BY report_id",
            (cohort_id,),
        ).fetchall()
        return {
            r["report_id"]: {
                "report_id": r["report_id"],
                "report_kind": r["report_kind"],
                **json.loads(r["report"]),
            }
            for r in rows
        }

    # ------------------------------------------------------------------
    # Command / event protocol (PRD §25)
    # ------------------------------------------------------------------

    def _current_revision(self, session_id: str) -> int:
        """Return the highest committed revision for this session, or 0."""
        row = self._conn.execute(
            "SELECT MAX(revision) AS rev FROM application_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["rev"] if row and row["rev"] is not None else 0

    def read_session_events(self, session_id: str) -> list[dict]:
        """Read ordered immutable commands; deduplicate command IDs and detect conflicts."""
        rows = self._conn.execute(
            "SELECT command_id, session_id, revision, expected_revision, "
            "command_digest, payload, sync_status, created_at "
            "FROM application_events WHERE session_id = ? ORDER BY revision",
            (session_id,),
        ).fetchall()
        return [
            {
                "command_id": r["command_id"],
                "session_id": r["session_id"],
                "revision": r["revision"],
                "expected_revision": r["expected_revision"],
                "command_digest": r["command_digest"],
                "payload": json.loads(r["payload"]),
                "sync_status": r["sync_status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def append_command(self, command: dict) -> dict:
        """Check command ID + expected revision, append one full event, confirm receipt.

        One API writer per session. On ambiguous timeout query command ID before retry.
        Return committed only after confirmation; offline cache returns pending_sync.
        """
        command_id = command["command_id"]
        session_id = command["session_id"]
        expected_revision = command["expected_revision"]
        payload = command["payload"]

        # 1. Idempotency: if the same command_id already exists, return its result.
        existing = self._conn.execute(
            "SELECT command_id, revision, command_digest, payload, sync_status, created_at "
            "FROM application_events WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if existing is not None:
            incoming_digest = digest(payload)
            if existing["command_digest"] != incoming_digest:
                raise DomainError(
                    "command_conflict",
                    f"Command {command_id!r} already exists with a different payload.",
                    409,
                )
            return {
                "command_id": existing["command_id"],
                "revision": existing["revision"],
                "sync_status": existing["sync_status"],
                "created_at": existing["created_at"],
                "duplicate": True,
            }

        # 2. Revision check: expected_revision must match the current revision.
        current_rev = self._current_revision(session_id)
        if expected_revision != current_rev:
            raise DomainError(
                "revision_conflict",
                f"Expected revision {expected_revision} but current is {current_rev}. "
                f"Re-read session state before retrying.",
                409,
            )

        # 3. Append the event.
        new_revision = current_rev + 1
        command_digest = digest(payload)
        now = datetime.now(UTC).isoformat()
        payload_json = canonical(payload)

        with self._conn:
            self._conn.execute(
                "INSERT INTO application_events "
                "(command_id, session_id, revision, expected_revision, "
                "command_digest, payload, sync_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (command_id, session_id, new_revision, expected_revision,
                 command_digest, payload_json, "pending_sync", now),
            )

        return {
            "command_id": command_id,
            "revision": new_revision,
            "sync_status": "pending_sync",
            "created_at": now,
            "duplicate": False,
        }

    def pending_commands(self, session_id: str) -> list[dict]:
        """Return all pending_sync commands in revision order, for Databricks replay."""
        rows = self._conn.execute(
            "SELECT command_id, session_id, revision, expected_revision, "
            "command_digest, payload, created_at "
            "FROM application_events "
            "WHERE session_id = ? AND sync_status = 'pending_sync' "
            "ORDER BY revision",
            (session_id,),
        ).fetchall()
        return [
            {
                "command_id": r["command_id"],
                "session_id": r["session_id"],
                "revision": r["revision"],
                "expected_revision": r["expected_revision"],
                "command_digest": r["command_digest"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def mark_synced(self, command_id: str) -> None:
        """Mark a command as successfully synced to Databricks."""
        with self._conn:
            affected = self._conn.execute(
                "UPDATE application_events SET sync_status = 'synced' "
                "WHERE command_id = ? AND sync_status = 'pending_sync'",
                (command_id,),
            ).rowcount
        if affected == 0:
            raise DomainError(
                "sync_not_found",
                f"Command {command_id!r} not found or already synced.",
                404,
            )

    # ------------------------------------------------------------------
    # Summary cache
    # ------------------------------------------------------------------

    def read_summary(self, cache_key: str) -> dict | None:
        """Cache key includes patient/evidence digest + prompt/generator versions."""
        row = self._conn.execute(
            "SELECT payload FROM summary_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def write_summary(self, cache_key: str, summary: dict) -> None:
        """Store validated text and evidence references; reconstructable after event commit."""
        patient_id = summary.get("patient_id", "")
        evidence_digest = summary.get("evidence_digest", "")
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO summary_cache "
                "(cache_key, patient_id, evidence_digest, payload) VALUES (?, ?, ?, ?)",
                (cache_key, patient_id, evidence_digest, canonical(summary)),
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
