"""Application service with durable persistence through the Repository protocol.

Snapshots, workflow transitions, overrides, and audit events survive restarts.
Every mutation goes through the command protocol (PRD §25): command ID + expected
revision → append immutable event → confirm receipt before responding.
"""

import csv
import io
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from threading import RLock

from hf_followup.domain.constants import INDICATOR_POLICY, METHODS, UNITS
from hf_followup.domain.errors import DomainError
from hf_followup.domain.indicators import organ_indicators
from hf_followup.domain.predictions import RISK_TASKS, ModelRisks
from hf_followup.domain.ranking import build_ranking
from hf_followup.repositories.bundle import digest
from hf_followup.services.summaries import template_summary

# Valid workflow transitions: from_state -> set of allowed to_states.
_TRANSITIONS = {
    "pending": {"reviewed"},
    "reviewed": {"contacted", "pending"},  # pending = reopen with reason.
    "contacted": {"pending"},  # reopen with reason required.
}


def synchronized(method):
    """Keep one session writer and its ranking reads atomic in the local API worker."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class ApplicationService:
    def __init__(self, cohort, benchmark: dict, settings, prediction_bundle=None, repository=None,
                 predictor_factory=None):
        self.cohort = cohort
        self.benchmark = benchmark
        self.settings = settings
        self.prediction_bundle = prediction_bundle
        self.predictions = prediction_bundle.ranking_predictions() if prediction_bundle else {}
        self.repo = repository
        self._lock = RLock()
        self._predictor_factory = predictor_factory
        self._predictor = None  # Reads use JSON; load trusted frozen pipelines only for changed facts.
        self.patient_risks = {
            pid: deepcopy(row["risks"]) for pid, row in prediction_bundle.patients.items()
        } if prediction_bundle else {}
        self._commands: dict[str, dict] = {}
        # A deleted highest ID must never be reassigned to a different patient.
        self._patient_sequence = max(int(pid[3:]) for pid in cohort.features)
        self._source_sequence = max(row["source_row"] for row in cohort.features.values())

        # Mutable session state rebuilt from events on startup.
        self.snapshots: dict[str, dict] = {}
        self.workflow: dict[str, str] = {}      # patient_id -> state
        self.overrides: dict[str, dict] = {}    # patient_id -> override dict
        self.revision: int = 0
        self._pin_sequence: int = 0

        # Replay persisted events if we have a repository.
        if self.repo:
            self._replay_events()

        # Always create a default snapshot so the API has something to serve.
        self.default_snapshot = self.create_snapshot(self._default_method(), 25)

    def _default_method(self) -> str:
        method = self.settings.default_method
        if method == "auto":
            return "patient_risk" if self.prediction_bundle else "points_v1"
        return method

    @contextmanager
    def session_read(self):
        """Bind composite evidence reads to one session revision during patient writes."""
        with self._lock:
            yield

    # ------------------------------------------------------------------
    # Event replay on startup
    # ------------------------------------------------------------------

    def _replay_events(self):
        """Rebuild in-memory state from persisted events."""
        events = self.repo.read_session_events(self.settings.session_id)
        for event in events:
            self._commands[event["command_id"]] = event
            payload = event["payload"]
            action = payload.get("action")
            self.revision = event["revision"]

            if action == "create_snapshot":
                self._apply_snapshot(payload)
            elif action == "workflow_transition":
                self._apply_workflow(payload)
            elif action == "override":
                self._apply_override(payload)
            elif action == "reset":
                self._apply_reset(payload)
            elif action == "add_patient":
                self._apply_add_patient(payload)
            elif action == "update_patient":
                self._apply_update_patient(payload)
            elif action == "delete_patient":
                self._apply_delete_patient(payload)

    def _apply_snapshot(self, payload: dict):
        """Rebuild a snapshot from its event payload."""
        if payload.get("model_bundle_id") and payload["model_bundle_id"] != self._bundle_id():
            return  # A promoted model publication requires a fresh snapshot/context.
        try:
            ranking = self._build_ranking(
                payload["method_id"], payload["capacity"], payload.get("mode", "operational")
            )
        except DomainError:
            return  # skip snapshots whose method was removed
        snapshot = {
            **ranking,
            "snapshot_id": payload["snapshot_id"],
            "created_at": payload["created_at"],
            "cohort_id": self.cohort.manifest["cohort_id"],
            "source_hash": self.cohort.manifest["source_hash"],
            "session_id": self.settings.session_id,
            "workflow_revision": self.revision,
            "workflow": dict(self.workflow),
            "overrides": dict(self.overrides),
            "provenance": payload.get("provenance", "persisted"),
            "sync_mode": payload.get("sync_mode", "persisted"),
            "model_bundle_id": self._bundle_id(),
        }
        self.snapshots[snapshot["snapshot_id"]] = snapshot

    def _apply_workflow(self, payload: dict):
        """Apply a workflow transition."""
        self.workflow[payload["patient_id"]] = payload["to_state"]

    def _apply_override(self, payload: dict):
        """Apply an override action."""
        action = payload["override_action"]
        patient_id = payload["patient_id"]
        if action == "reset":
            self.overrides.pop(patient_id, None)
        else:
            seq = payload.get("sequence", self._pin_sequence + 1)
            self.overrides[patient_id] = {
                "action": action,
                "reason": payload["reason"],
                "sequence": seq,
                "actor": payload.get("actor", "clinician"),
            }
            if action == "pin":
                self._pin_sequence = max(self._pin_sequence, seq)

    def _apply_reset(self, payload: dict):
        """Apply a session reset — clear workflow and overrides but keep audit trail."""
        self.workflow.clear()
        self.overrides.clear()
        self.snapshots.clear()
        self._pin_sequence = 0

    def _apply_add_patient(self, payload: dict):
        """Replay a patient addition."""
        pid = payload["patient_id"]
        self.cohort.features[pid] = {
            "patient_id": pid,
            "source_row": payload["source_row"],
            "facts": payload["facts"],
        }
        self._patient_sequence = max(self._patient_sequence, int(pid[3:]))
        self._source_sequence = max(self._source_sequence, payload["source_row"])
        self._apply_risks(pid, payload["facts"], payload)
        self.cohort.manifest["accepted_ids"] = list(self.cohort.features.keys())
        self.cohort.manifest["accepted_count"] = len(self.cohort.features)
        self.cohort.manifest["source_count"] = len(self.cohort.features)

    def _apply_update_patient(self, payload: dict):
        """Replay a patient update."""
        pid = payload["patient_id"]
        if pid in self.cohort.features:
            self.cohort.features[pid]["facts"] = payload["updated_facts"]
            self._apply_risks(pid, payload["updated_facts"], payload)

    def _apply_delete_patient(self, payload: dict):
        """Replay a patient deletion."""
        pid = payload["patient_id"]
        self.cohort.features.pop(pid, None)
        self.patient_risks.pop(pid, None)
        for model in self.predictions.values():
            model["patients"].pop(pid, None)
        self.cohort.manifest["accepted_ids"] = list(self.cohort.features.keys())
        self.cohort.manifest["accepted_count"] = len(self.cohort.features)
        self.cohort.manifest["source_count"] = len(self.cohort.features)
        self.workflow.pop(pid, None)
        self.overrides.pop(pid, None)

    # ------------------------------------------------------------------
    # Command protocol
    # ------------------------------------------------------------------

    def _execute_command(self, command_id: str, expected_revision: int, payload: dict) -> dict:
        """Run a mutation through the command protocol.

        If no repository is configured, executes in memory only.
        """
        if self.repo:
            result = self.repo.append_command({
                "command_id": command_id,
                "session_id": self.settings.session_id,
                "expected_revision": expected_revision,
                "payload": payload,
            })
            if result["duplicate"]:
                return result
            self.revision = result["revision"]
            self._commands[command_id] = {**result, "payload": deepcopy(payload)}
            return result
        else:
            # In-memory only fallback (no persistence).
            if expected_revision != self.revision:
                raise DomainError(
                    "revision_conflict",
                    f"Expected revision {expected_revision} but current is {self.revision}.",
                    409,
                )
            self.revision += 1
            result = {
                "command_id": command_id,
                "revision": self.revision,
                "sync_status": "in_memory",
                "created_at": datetime.now(UTC).isoformat(),
                "duplicate": False,
            }
            self._commands[command_id] = {**result, "payload": deepcopy(payload)}
            return result

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    @synchronized
    def create_snapshot(self, method_id: str, capacity: int, mode="operational") -> dict:
        """Freeze a ranking in memory; create_snapshot_command journals its identity."""
        ranking = self._build_ranking(method_id, capacity, mode)
        snapshot = {
            **ranking,
            "snapshot_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "cohort_id": self.cohort.manifest["cohort_id"],
            "source_hash": self.cohort.manifest["source_hash"],
            "session_id": self.settings.session_id,
            "workflow_revision": self.revision,
            "workflow": dict(self.workflow),
            "overrides": dict(self.overrides),
            "provenance": "persisted" if self.repo else "in_memory",
            "sync_mode": "persisted" if self.repo else "in_memory_scaffold",
            "model_bundle_id": self.prediction_bundle.manifest["bundle_id"]
            if self.prediction_bundle
            else None,
        }
        self.snapshots[snapshot["snapshot_id"]] = snapshot
        return snapshot

    @synchronized
    def create_snapshot_command(self, command_id: str, expected_revision: int,
                                method_id: str, capacity: int, mode: str = "operational") -> dict:
        """Create a snapshot through the command protocol."""
        snapshot = self.create_snapshot(method_id, capacity, mode)
        payload = {
            "action": "create_snapshot",
            "snapshot_id": snapshot["snapshot_id"],
            "method_id": method_id,
            "capacity": capacity,
            "mode": mode,
            "created_at": snapshot["created_at"],
            "provenance": snapshot["provenance"],
            "sync_mode": snapshot["sync_mode"],
            "model_bundle_id": snapshot["model_bundle_id"],
        }
        result = self._execute_command(command_id, expected_revision, payload)
        # Update snapshot with the committed revision.
        snapshot["workflow_revision"] = self.revision
        self.snapshots[snapshot["snapshot_id"]] = snapshot
        return {
            "snapshot": snapshot,
            "revision": result["revision"],
            "sync_status": result["sync_status"],
            "replayed": result["duplicate"],
        }

    def snapshot(self, snapshot_id: str) -> dict:
        if snapshot_id not in self.snapshots:
            raise DomainError(
                "snapshot_not_found",
                "Snapshot does not exist; refresh after an API restart.",
                404,
            )
        return self.snapshots[snapshot_id]

    # ------------------------------------------------------------------
    # Workflow transitions
    # ------------------------------------------------------------------

    @synchronized
    def transition_workflow(self, command_id: str, expected_revision: int,
                            patient_id: str, to_state: str,
                            reason: str | None = None) -> dict:
        """Transition a patient's workflow state with validation."""
        if patient_id not in self.cohort.features:
            raise DomainError("patient_not_found", "Patient does not exist.", 404)

        current_state = self.workflow.get(patient_id, "pending")
        allowed = _TRANSITIONS.get(current_state, set())

        if to_state not in allowed:
            raise DomainError(
                "invalid_transition",
                f"Cannot transition from {current_state!r} to {to_state!r}. "
                f"Allowed: {sorted(allowed)}.",
                422,
            )

        # Reopening (back to pending) requires a reason.
        if to_state == "pending" and current_state in {"reviewed", "contacted"}:
            if not reason:
                raise DomainError(
                    "reason_required",
                    f"Reopening a {current_state} patient requires a reason.",
                    422,
                )

        payload = {
            "action": "workflow_transition",
            "patient_id": patient_id,
            "from_state": current_state,
            "to_state": to_state,
            "reason": reason,
        }
        result = self._execute_command(command_id, expected_revision, payload)

        if not result["duplicate"]:
            self.workflow[patient_id] = to_state

        return {
            "patient_id": patient_id,
            "from_state": current_state,
            "to_state": to_state,
            "revision": result["revision"],
            "sync_status": result["sync_status"],
        }

    # ------------------------------------------------------------------
    # Overrides (pin / defer / reset)
    # ------------------------------------------------------------------

    @synchronized
    def apply_override(self, command_id: str, expected_revision: int,
                       patient_id: str, action: str, reason: str,
                       session_id: str | None = None) -> dict:
        """Apply a clinician override (pin, defer, or reset)."""
        if patient_id not in self.cohort.features:
            raise DomainError("patient_not_found", "Patient does not exist.", 404)

        current_state = self.workflow.get(patient_id, "pending")

        if action == "pin":
            # Contacted patients must be reopened before pinning.
            if current_state == "contacted":
                raise DomainError(
                    "contacted_pin_blocked",
                    "Contacted patient must be reopened before pinning.",
                    422,
                )
            # Check existing override.
            existing = self.overrides.get(patient_id, {})
            if existing.get("action") == "defer":
                raise DomainError(
                    "override_conflict",
                    "Patient is deferred; reset the override before pinning.",
                    409,
                )
            # Check capacity: count current pins + this new one.
            current_pins = sum(
                1 for o in self.overrides.values() if o.get("action") == "pin"
            )
            if existing.get("action") != "pin":
                current_pins += 1
            # We don't know the capacity here, but build_ranking will reject it.
            # We do a pre-check with the default snapshot's capacity.
            if self.default_snapshot and current_pins > self.default_snapshot["capacity"]:
                raise DomainError(
                    "pin_capacity_conflict",
                    "Capacity cannot be smaller than the active pin count.",
                    409,
                )
            self._pin_sequence += 1
            sequence = self._pin_sequence
        elif action == "defer":
            existing = self.overrides.get(patient_id, {})
            if existing.get("action") == "pin":
                raise DomainError(
                    "override_conflict",
                    "Patient is pinned; reset the override before deferring.",
                    409,
                )
            sequence = 0
        elif action == "reset":
            if patient_id not in self.overrides:
                raise DomainError(
                    "no_override",
                    "Patient has no active override to reset.",
                    422,
                )
            sequence = 0
        else:
            raise DomainError("invalid_action", f"Unknown override action: {action!r}.", 422)

        payload = {
            "action": "override",
            "patient_id": patient_id,
            "override_action": action,
            "reason": reason,
            "sequence": sequence,
            "actor": session_id or self.settings.session_id,
        }
        result = self._execute_command(command_id, expected_revision, payload)

        if not result["duplicate"]:
            self._apply_override(payload)

        return {
            "patient_id": patient_id,
            "override_action": action,
            "revision": result["revision"],
            "sync_status": result["sync_status"],
        }

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    @synchronized
    def reset_session(self, command_id: str, expected_revision: int,
                      reason: str) -> dict:
        """Reset the session: clear workflow and overrides, keep the audit trail."""
        payload = {
            "action": "reset",
            "reason": reason,
            "session_id": self.settings.session_id,
        }
        result = self._execute_command(command_id, expected_revision, payload)

        if not result["duplicate"]:
            self._apply_reset(payload)
            # Recreate the default snapshot after reset.
            self.default_snapshot = self.create_snapshot(self._default_method(), 25)

        return {
            "revision": result["revision"],
            "sync_status": result["sync_status"],
        }

    # ------------------------------------------------------------------
    # Patient CRUD
    # ------------------------------------------------------------------

    def _bundle_id(self):
        return self.prediction_bundle.manifest["bundle_id"] if self.prediction_bundle else None

    def _build_ranking(self, method_id, capacity, mode="operational"):
        ranking = build_ranking(
            self.cohort.features, self.workflow, self.overrides, method_id, capacity,
            mode=mode, predictions=self.predictions,
        )
        # Freeze all three outputs beside the same baseline facts. Neither a later
        # edit nor a different queue mode may substitute another version's scores.
        for row in ranking["rows"]:
            row["facts"] = deepcopy(row["facts"])
            row["model_risks"] = deepcopy(self.patient_risks.get(row["patient_id"]))
        return ranking

    def _infer_risks(self, facts: dict):
        if not self.prediction_bundle:
            return None  # Explicit points-only mode; never fabricate ML outputs.
        try:
            if self._predictor is None:
                if self._predictor_factory is None:
                    raise ValueError("No frozen inference factory configured")
                self._predictor = self._predictor_factory()
            risks = ModelRisks.model_validate(self._predictor.predict_patient(facts)).model_dump()
            if risks["bundle_id"] != self._bundle_id():
                raise ValueError("Inference and read-cache bundle versions differ")
            return risks
        except Exception as error:
            raise DomainError(
                "inference_unavailable",
                "Frozen ML scoring failed; no patient changes were saved. "
                "Check the published artifacts and pinned ML dependencies.", 503,
            ) from error

    def _apply_risks(self, pid: str, facts: dict, payload: dict):
        if not self.prediction_bundle:
            return
        risks = payload.get("model_risks")
        # Old events may predate this interface or belong to a previous publication.
        # Re-score those facts using the current frozen models on replay, never fit.
        if not risks or risks.get("bundle_id") != self._bundle_id() or (
            payload.get("features_digest") != digest(facts)
        ):
            risks = self._infer_risks(facts)
        risks = ModelRisks.model_validate(risks).model_dump()
        self.patient_risks[pid] = risks
        for task in RISK_TASKS:
            self.predictions[task]["patients"][pid] = risks[task]

    def _patient_retry(self, command_id: str, request: dict):
        event = self._commands.get(command_id)
        if event is None:
            return None
        payload = event["payload"]
        if payload.get("request") != request:
            raise DomainError("command_conflict", "Command ID was already used for another request.", 409)
        return self._patient_receipt(payload, event)

    def _patient_receipt(self, payload, result):
        response = {
            "patient_id": payload["patient_id"], "revision": result["revision"],
            "sync_status": result["sync_status"],
            "model_risks": payload.get("model_risks"),
        }
        if payload["action"] != "delete_patient":
            response["facts"] = payload.get("updated_facts", payload.get("facts"))
        return response

    def _check_revision(self, expected_revision):
        if expected_revision != self.revision:
            raise DomainError("revision_conflict", "Patient data changed; refresh before retrying.", 409)

    @synchronized
    def add_patient(self, command_id: str, expected_revision: int, facts: dict) -> dict:
        """Score all three frozen pipelines before durably appending baseline facts."""
        request = {"action": "add_patient", "facts": facts}
        if previous := self._patient_retry(command_id, request):
            return previous
        self._check_revision(expected_revision)
        if self._patient_sequence >= 9999:
            raise DomainError("patient_id_capacity", "The session has exhausted its patient IDs.", 409)
        risks = self._infer_risks(facts)  # Fail atomically before the command is written.
        payload = {
            **request, "request": request, "patient_id": f"HF-{self._patient_sequence + 1:04d}",
            "source_row": self._source_sequence + 1,
            "features_digest": digest(facts), "model_risks": risks,
        }
        result = self._execute_command(command_id, expected_revision, payload)
        self._apply_add_patient(payload)
        self.default_snapshot = self.create_snapshot(self._default_method(), 25)
        return self._patient_receipt(payload, result)

    @synchronized
    def update_patient(self, command_id: str, expected_revision: int,
                       patient_id: str, updates: dict) -> dict:
        """Re-score the complete baseline; old snapshots retain their own risk objects."""
        request = {"action": "update_patient", "patient_id": patient_id, "updates": updates}
        if previous := self._patient_retry(command_id, request):
            return previous
        self._check_revision(expected_revision)
        if patient_id not in self.cohort.features:
            raise DomainError("patient_not_found", "Patient does not exist.", 404)
        facts = self.cohort.features[patient_id]["facts"]
        updated = {**facts, **updates}
        risks = self._infer_risks(updated)
        payload = {
            **request, "request": request, "previous_facts": facts, "updated_facts": updated,
            "features_digest": digest(updated), "model_risks": risks,
        }
        result = self._execute_command(command_id, expected_revision, payload)
        self._apply_update_patient(payload)
        self.default_snapshot = self.create_snapshot(self._default_method(), 25)
        return self._patient_receipt(payload, result)

    @synchronized
    def delete_patient(self, command_id: str, expected_revision: int,
                       patient_id: str, reason: str) -> dict:
        """Remove live facts, workflow and prediction indexes; retain immutable audit events."""
        request = {"action": "delete_patient", "patient_id": patient_id, "reason": reason}
        if previous := self._patient_retry(command_id, request):
            return previous
        self._check_revision(expected_revision)
        if patient_id not in self.cohort.features:
            raise DomainError("patient_not_found", "Patient does not exist.", 404)
        payload = {**request, "request": request}
        result = self._execute_command(command_id, expected_revision, payload)
        self._apply_delete_patient(payload)
        self.default_snapshot = self.create_snapshot(self._default_method(), 25)
        return self._patient_receipt(payload, result)

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    def audit_events(self, limit: int = 50, offset: int = 0) -> dict:
        """Return ordered, paginated audit events."""
        if self.repo:
            events = self.repo.read_session_events(self.settings.session_id)
        else:
            events = []

        # Strip any sensitive fields before returning.
        safe_events = []
        for event in events:
            safe_events.append({
                "command_id": event["command_id"],
                "session_id": event["session_id"],
                "revision": event["revision"],
                "action": event["payload"].get("action"),
                "payload": {
                    k: v for k, v in event["payload"].items()
                    if k not in {"token", "credential", "secret"}
                },
                "created_at": event["created_at"],
                "sync_status": event.get("sync_status", "unknown"),
            })

        total = len(safe_events)
        page = safe_events[offset:offset + limit]
        return {
            "events": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "session_id": self.settings.session_id,
        }

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_queue_csv(self, snapshot_id: str) -> str:
        """Export the exact snapshot as a CSV string with formula neutralization."""
        snapshot = self.snapshot(snapshot_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "call_rank", "patient_id", "score", "score_kind", "priority_band",
            "reason", "workflow_state", "override_action",
            "age", "ejection_fraction", "serum_creatinine",
            "method_id", "cohort_id", "source_hash", "snapshot_id",
        ])
        for row in snapshot["queue"]:
            writer.writerow([
                row["call_rank"],
                _safe_csv(row["patient_id"]),
                row["score"]["value"],
                row["score"]["kind"],
                _safe_csv(row["priority_band"]),
                _safe_csv(row["reason"]),
                _safe_csv(row["workflow_state"]),
                _safe_csv(row["override"]["action"] if row["override"] else ""),
                row["facts"]["age"],
                row["facts"]["ejection_fraction"],
                row["facts"]["serum_creatinine"],
                _safe_csv(snapshot["method_id"]),
                _safe_csv(snapshot["cohort_id"]),
                snapshot["source_hash"],
                snapshot["snapshot_id"],
            ])
        return output.getvalue()

    # ------------------------------------------------------------------
    # Shared snapshot/evidence reads
    # ------------------------------------------------------------------

    @synchronized
    def cohort_read(self) -> dict:
        return {
            **self.cohort.manifest,
            "eligible_count": len(self.cohort.features),
            "workflow_revision": self.revision,
            "current_snapshot_id": self.default_snapshot["snapshot_id"],
            "session_id": self.settings.session_id,
            "provenance": "persisted" if self.repo else "local_csv_scaffold",
            "sync_mode": "persisted" if self.repo else "in_memory_scaffold",
        }

    def models(self) -> dict:
        manifest = self.prediction_bundle.manifest if self.prediction_bundle else None
        supervised = None
        if self.prediction_bundle:
            report = self.prediction_bundle.report
            supervised = {
                "evaluation_mode": "exploratory_held_out_test",
                "development_n": len(report["split"]["development_ids"]),
                "test_n": len(report["split"]["test_ids"]),
                "selection": report["selection"],
                "tasks": report["tasks"],
                "limitations": report["limitations"],
            }
        return {
            "methods": [
                {
                    "method_id": method,
                    "label": method.replace("_", " "),
                    "score_kind": "points" if method.startswith("points") else "model_output",
                    "available": True,
                }
                for method in (*METHODS, *self.predictions)
            ],
            "reports": {"benchmark": self.benchmark, "supervised": supervised},
            "supervised_status": "ready" if manifest else "not_published",
            "bundle_id": manifest["bundle_id"] if manifest else None,
            "selected_models": manifest["models"] if manifest else {},
        }

    @synchronized
    def patient(self, patient_id: str, snapshot_id: str) -> dict:
        if patient_id not in self.cohort.features:
            raise DomainError(
                "patient_not_found", "Patient does not exist in the active cohort.", 404
            )
        snapshot = self.snapshot(snapshot_id)
        row = next((row for row in snapshot["rows"] if row["patient_id"] == patient_id), None)
        if row is None:
            raise DomainError("patient_not_in_snapshot", "Patient is absent from this snapshot.", 404)
        facts = row["facts"]
        measurements = [
            {
                "id": "ef_measurement",
                "field": "ejection_fraction",
                "value": facts["ejection_fraction"],
                "unit": "%",
                "predicate": "recorded EF",
                "scale": "measurement",
            },
            {
                "id": "creatinine_measurement",
                "field": "serum_creatinine",
                "value": facts["serum_creatinine"],
                "unit": "mg/dL",
                "predicate": "recorded creatinine",
                "scale": "measurement",
            },
        ]

        # Use actual workflow/override state.
        wf_state = self.workflow.get(patient_id, "pending")
        override = self.overrides.get(patient_id)

        patient = {
            "patient_id": patient_id,
            "cohort_id": snapshot["cohort_id"],
            "ranking_snapshot_id": snapshot_id,
            "method_id": snapshot["method_id"],
            "model_rank": row["model_rank"],
            "call_rank": row["call_rank"] if row["in_queue"] else None,
            "priority_band": row["priority_band"],
            "score": row["score"],
            "facts": facts,
            "evidence": [*measurements, *row["score"]["evidence"]],
            "organs": organ_indicators(facts),
            "indicator_policy_version": INDICATOR_POLICY,
            "explanation_method": row["score"]["explanation_method"],
            "workflow": {"state": wf_state, "revision": self.revision},
            "override": override,
            "provenance": "persisted" if self.repo else "local_csv_scaffold",
            "summary_status": "template",
            "fact_units": UNITS,
            "model_risks": row.get("model_risks"),
        }
        # One evidence namespace for summaries/tools. Logistic entries are real scaled
        # log-odds contributions; forest entries are observations, not local attribution.
        if patient["model_risks"]:
            evidence = {item["id"]: item for item in patient["evidence"]}
            for task in self.prediction_bundle.manifest["models"]:
                evidence.update(
                    {item["id"]: item for item in patient["model_risks"][task]["evidence"]}
                )
            patient["evidence"] = list(evidence.values())
        patient["evidence_digest"] = digest(patient)
        patient["summary"] = template_summary(patient)
        return patient


def _safe_csv(value: str) -> str:
    """Neutralize spreadsheet formula injection (PRD OPS-01).

    Cells starting with =, +, -, or @ get a leading tab character so spreadsheets
    treat them as text instead of formulas.
    """
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@"):
        return "\t" + s
    return s
