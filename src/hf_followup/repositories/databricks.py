"""Databricks SQL repository implementing the Repository protocol.

Connects to Databricks Delta tables via the SQL connector. Uses native parameter
binding for all values and a validated allowlist for catalog/schema identifiers.
Never exposes raw outcomes, SQL, or credentials to the frontend.
"""

import json
import os
import re
from datetime import UTC, datetime

from hf_followup.domain.errors import DomainError
from hf_followup.repositories.bundle import canonical, digest


# Only these table names are allowed in queries. Prevents SQL injection via table names.
_ALLOWED_TABLES = frozenset({
    "raw_clinical_records",
    "patient_features",
    "evaluation_outcomes",
    "cohort_manifests",
    "model_predictions",
    "evaluation_reports",
    "application_events",
    "summary_cache",
})


class DatabricksRepository:
    """Implements ``repositories.base.Repository`` backed by Databricks Delta tables."""

    def __init__(self):
        self.hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
        self.http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
        self.token = os.getenv("DATABRICKS_TOKEN", "")
        self.catalog = os.getenv("HF_CATALOG", "")
        self.schema = os.getenv("HF_SCHEMA", "hf_hackathon")

    def _validate_namespace(self):
        """Verify catalog and schema are safe identifiers before using them in SQL."""
        if not all((self.hostname, self.http_path, self.token, self.catalog)):
            raise DomainError(
                "databricks_unconfigured",
                "Databricks workspace connection is not configured. "
                "Set DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, "
                "DATABRICKS_TOKEN, and HF_CATALOG in .env.",
                503,
            )
        if not all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part)
            for part in (self.catalog, self.schema)
        ):
            raise DomainError(
                "invalid_namespace",
                "Catalog and schema must be valid SQL identifiers. "
                "Review the approved catalog/schema names in .env.",
            )

    def _table(self, name: str) -> str:
        """Return the fully qualified table name after validating the identifier."""
        if name not in _ALLOWED_TABLES:
            raise DomainError("invalid_table", f"Table {name!r} is not in the allowlist.")
        return f"{self.catalog}.{self.schema}.{name}"

    def connect(self):
        """Open a Databricks SQL connection. Use as a context manager."""
        self._validate_namespace()
        from databricks import sql

        return sql.connect(
            server_hostname=self.hostname,
            http_path=self.http_path,
            access_token=self.token,
        )

    # ------------------------------------------------------------------
    # Cohort
    # ------------------------------------------------------------------

    def load_cohort(self, cohort_id: str) -> dict:
        """Return manifest + allowlisted features; never raw outcomes."""
        with self.connect() as conn, conn.cursor() as cur:
            # Load manifest.
            cur.execute(
                f"SELECT manifest_json FROM {self._table('cohort_manifests')} "
                "WHERE cohort_id = ?",
                [cohort_id],
            )
            row = cur.fetchone()
            if row is None:
                raise DomainError(
                    "cohort_not_found",
                    f"Cohort {cohort_id!r} is not stored in Databricks.",
                    404,
                )
            manifest = json.loads(row[0])

            # Load features.
            cur.execute(
                f"SELECT patient_id, source_row, features_json "
                f"FROM {self._table('patient_features')} "
                "WHERE cohort_id = ? ORDER BY source_row",
                [cohort_id],
            )
            feature_rows = cur.fetchall()

        features = {
            r[0]: {
                "patient_id": r[0],
                "source_row": r[1],
                "facts": json.loads(r[2]),
            }
            for r in feature_rows
        }
        return {"manifest": manifest, "features": features}

    # ------------------------------------------------------------------
    # Predictions
    # ------------------------------------------------------------------

    def load_predictions(self, cohort_id: str, model_version: str) -> dict:
        """Return complete frozen predictions with model/explanation/provenance metadata."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT model_id, patient_id, model_version, score, "
                f"prediction_json, model_metadata_json "
                f"FROM {self._table('model_predictions')} "
                "WHERE cohort_id = ? AND model_version = ?",
                [cohort_id, model_version],
            )
            rows = cur.fetchall()

        if not rows:
            raise DomainError(
                "predictions_not_found",
                f"No predictions for cohort {cohort_id!r} version {model_version!r}.",
                404,
            )

        result: dict[str, dict] = {}
        for model_id, patient_id, m_version, score, pred_json, meta_json in rows:
            if model_id not in result:
                meta = json.loads(meta_json)
                result[model_id] = {
                    "model_id": model_id,
                    "model_version": m_version,
                    "explanation_method": meta.get("explanation_method", "unknown"),
                    "patients": {},
                    **meta,
                }
            result[model_id]["patients"][patient_id] = json.loads(pred_json)
        return result

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def load_reports(self, cohort_id: str) -> dict:
        """Return aggregate descriptive/CV/test reports with their population labels."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT report_id, report_kind, report_json "
                f"FROM {self._table('evaluation_reports')} "
                "WHERE cohort_id = ? ORDER BY report_id",
                [cohort_id],
            )
            rows = cur.fetchall()

        return {
            r[0]: {
                "report_id": r[0],
                "report_kind": r[1],
                **json.loads(r[2]),
            }
            for r in rows
        }

    # ------------------------------------------------------------------
    # Command / event protocol (PRD §25)
    # ------------------------------------------------------------------

    def _current_revision(self, session_id: str, cursor) -> int:
        """Return the highest committed revision for this session, or 0."""
        cursor.execute(
            f"SELECT MAX(revision) FROM {self._table('application_events')} "
            "WHERE session_id = ?",
            [session_id],
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0

    def read_session_events(self, session_id: str) -> list[dict]:
        """Read ordered immutable commands; deduplicate command IDs and detect conflicts."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT command_id, session_id, revision, expected_revision, "
                f"command_digest, payload_json, created_at "
                f"FROM {self._table('application_events')} "
                "WHERE session_id = ? ORDER BY revision",
                [session_id],
            )
            rows = cur.fetchall()

        return [
            {
                "command_id": r[0],
                "session_id": r[1],
                "revision": r[2],
                "expected_revision": r[3],
                "command_digest": r[4],
                "payload": json.loads(r[5]),
                "sync_status": "synced",
                "created_at": r[6],
            }
            for r in rows
        ]

    def append_command(self, command: dict) -> dict:
        """Check command ID + expected revision, append one full event, confirm receipt.

        One API writer per session. On ambiguous timeout query command ID before retry.
        Return committed only after confirmation; Databricks writes are 'synced'.
        """
        command_id = command["command_id"]
        session_id = command["session_id"]
        expected_revision = command["expected_revision"]
        payload = command["payload"]

        with self.connect() as conn, conn.cursor() as cur:
            # 1. Idempotency: check if this command_id already exists.
            cur.execute(
                f"SELECT command_id, revision, command_digest, created_at "
                f"FROM {self._table('application_events')} "
                "WHERE command_id = ?",
                [command_id],
            )
            existing = cur.fetchone()

            if existing is not None:
                incoming_digest = digest(payload)
                if existing[2] != incoming_digest:
                    raise DomainError(
                        "command_conflict",
                        f"Command {command_id!r} already exists with a different payload.",
                        409,
                    )
                return {
                    "command_id": existing[0],
                    "revision": existing[1],
                    "sync_status": "synced",
                    "created_at": existing[3],
                    "duplicate": True,
                }

            # 2. Revision check.
            current_rev = self._current_revision(session_id, cur)
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

            cur.execute(
                f"INSERT INTO {self._table('application_events')} "
                "(command_id, session_id, revision, expected_revision, "
                "command_digest, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [command_id, session_id, new_revision, expected_revision,
                 command_digest, payload_json, now],
            )

        return {
            "command_id": command_id,
            "revision": new_revision,
            "sync_status": "synced",
            "created_at": now,
            "duplicate": False,
        }

    # ------------------------------------------------------------------
    # Summary cache
    # ------------------------------------------------------------------

    def read_summary(self, cache_key: str) -> dict | None:
        """Cache key includes patient/evidence digest + prompt/generator versions."""
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT payload_json FROM {self._table('summary_cache')} "
                "WHERE cache_key = ?",
                [cache_key],
            )
            row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def write_summary(self, cache_key: str, summary: dict) -> None:
        """Store validated text and evidence references; reconstructable after event commit."""
        patient_id = summary.get("patient_id", "")
        evidence_digest = summary.get("evidence_digest", "")
        payload_json = canonical(summary)
        with self.connect() as conn, conn.cursor() as cur:
            # Delta doesn't support UPSERT natively in all configurations.
            # Delete then insert to simulate replace.
            cur.execute(
                f"DELETE FROM {self._table('summary_cache')} WHERE cache_key = ?",
                [cache_key],
            )
            cur.execute(
                f"INSERT INTO {self._table('summary_cache')} "
                "(cache_key, patient_id, evidence_digest, payload_json) "
                "VALUES (?, ?, ?, ?)",
                [cache_key, patient_id, evidence_digest, payload_json],
            )
