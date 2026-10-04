"""ElevenLabs adapter and read-only voice tools (PRD §17).

Client tools call these routes from the browser; ElevenLabs never needs access to
localhost. Short-lived opaque grants bind requests to the displayed snapshot.
They are not user accounts: this is the existing single-user local demo boundary.
Run one API worker, as required by the application's command protocol.
"""

import logging
import secrets
import time
from collections import deque
from threading import RLock
from urllib.parse import urlparse

import httpx

from hf_followup.api.schemas import PatientRead, QueueRow
from hf_followup.domain.errors import DomainError

LOG = logging.getLogger(__name__)
READ_TOOLS = frozenset({"get_queue", "get_patient", "explain_priority", "get_comparison", "preview_heart_weight"})
LIMITATIONS = [
    "Follow-up prioritization is not a diagnosis or treatment recommendation.",
    "Organ indicators use prototype measurement thresholds, not organ-model probabilities.",
    "Individual historical outcomes, symptoms, medicines, and contact details are unavailable.",
]


class VoiceService:
    def __init__(self, settings, application, client: httpx.AsyncClient):
        self.settings, self.application, self.client = settings, application, client
        self._grants: dict[str, dict] = {}
        self._requests: dict[str, deque] = {}
        self._lock = RLock()

    @property
    def configured(self) -> bool:
        return bool(self.settings.elevenlabs_api_key and self.settings.elevenlabs_agent_id)

    def require_origin(self, origin: str | None):
        # CORS alone does not prevent cross-site requests from spending credits.
        # Non-browser clients must deliberately send the configured local origin.
        if not origin or origin not in self.settings.origins:
            raise DomainError("voice_origin_denied", "Open the dashboard from an allowed origin.", 403)

    def rate_limit(self, address: str):
        now = time.monotonic()
        with self._lock:
            self._requests = {key: entries for key, entries in self._requests.items() if entries and entries[-1] > now - 60}
            if len(self._requests) >= 1024 and address not in self._requests:
                raise DomainError("voice_rate_limited", "Voice session limit reached. Try again shortly.", 429, True)
            entries = self._requests.setdefault(address, deque())
            while entries and entries[0] <= now - 60:
                entries.popleft()
            if len(entries) >= self.settings.voice_session_requests_per_minute:
                raise DomainError("voice_rate_limited", "Voice session limit reached. Try again shortly.", 429, True)
            entries.append(now)

    def validate_context(self, snapshot_id: str, patient_id: str | None):
        snapshot = self.application.snapshot(snapshot_id)
        if snapshot["session_id"] != self.settings.session_id:
            raise DomainError("voice_context_denied", "Snapshot belongs to another session.", 403)
        # PatientRead includes current workflow state. Refuse old snapshots rather
        # than mixing newer workflow facts into an older spoken ranking.
        if snapshot["workflow_revision"] != self.application.revision:
            raise DomainError("stale_voice_context", "Queue changed. Refresh the dashboard before reconnecting.", 409)
        if patient_id and not any(row["patient_id"] == patient_id for row in snapshot["rows"]):
            raise DomainError("patient_not_in_snapshot", "Patient is not present in this ranking snapshot.", 404)
        return snapshot

    def context(self, body) -> dict:
        snapshot = self.validate_context(body.snapshot_id, body.patient_id)
        now = time.time()
        grant = {
            "snapshot_id": body.snapshot_id,
            "patient_id": body.patient_id,
            "cohort_id": snapshot["cohort_id"],
            "method_id": snapshot["method_id"],
            "expires_at": now + self.settings.voice_max_duration_seconds,
            "max_duration_seconds": self.settings.voice_max_duration_seconds,
        }
        with self._lock:
            self._grants = {key: value for key, value in self._grants.items() if value["expires_at"] > now}
            if len(self._grants) >= 256:
                raise DomainError("voice_capacity_reached", "Too many active voice contexts. Try again shortly.", 429, True)
            token = secrets.token_urlsafe(32)
            self._grants[token] = grant
        return {**grant, "tool_token": token}

    async def session(self, body) -> dict:
        self.validate_context(body.snapshot_id, body.patient_id)
        if not self.configured:
            raise DomainError("voice_unconfigured", "Set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID in the server .env file.", 503)
        try:
            response = await self.client.get(
                "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                params={"agent_id": self.settings.elevenlabs_agent_id},
                headers={"xi-api-key": self.settings.elevenlabs_api_key},
            )
        except httpx.RequestError:
            raise DomainError("voice_provider_unavailable", "ElevenLabs could not be reached. Text evidence remains available.", 503, True) from None
        # Never forward provider bodies: errors may contain configuration/secrets.
        if response.status_code in {401, 403}:
            raise DomainError("voice_provider_auth", "ElevenLabs rejected the server credentials or agent permissions.", 503)
        if response.status_code == 429:
            raise DomainError("voice_provider_limit", "ElevenLabs usage or concurrency limit reached.", 503, True)
        if response.is_error:
            raise DomainError("voice_provider_unavailable", "ElevenLabs could not start a session.", 503, True)
        try:
            signed_url = response.json()["signed_url"]
            url = urlparse(signed_url)
            if url.scheme != "wss" or url.hostname != "api.elevenlabs.io":
                raise ValueError("Invalid provider URL")
        except (ValueError, KeyError, TypeError):
            raise DomainError("voice_provider_response", "ElevenLabs returned an invalid session response.", 502) from None
        return {**self.context(body), "signed_url": signed_url, "connection_type": "websocket", "text_only": body.text_only}

    def tool(self, name: str, body, token: str | None) -> dict:
        if name not in READ_TOOLS:
            raise DomainError("voice_tool_denied", "Only read-only evidence tools are permitted here.", 403)
        with self._lock:
            grant = self._grants.get(token or "")
        if not grant or grant["expires_at"] <= time.time():
            raise DomainError("voice_context_expired", "Reconnect or refresh the voice context.", 401)
        if body.snapshot_id != grant["snapshot_id"] or body.cohort_id != grant["cohort_id"]:
            raise DomainError("voice_context_mismatch", "Tool request does not match its authorized snapshot.", 409)
        snapshot = self.validate_context(body.snapshot_id, body.patient_id)
        result = {
            "snapshot_id": body.snapshot_id,
            "cohort_id": grant["cohort_id"],
            "method_id": grant["method_id"],
            "source": snapshot["provenance"],
            "limitations": LIMITATIONS,
        }
        if name == "get_queue":
            rows = snapshot["queue"][:body.limit]
            # A short deterministic script keeps the 20–40 second briefing from
            # growing into an exhaustive recitation of ranks and every fact.
            briefing = [f"The first {len(rows)} patients in this follow-up queue are:"]
            for row in rows:
                facts = row["facts"]
                phrase = f"{row['patient_id']}, call rank {row['call_rank']}, {row['score']['value']:g} {row['score']['label']}."
                phrase += f" Recorded ejection fraction is {facts['ejection_fraction']:g}%."
                if len(rows) <= 3:
                    phrase += f" Creatinine is {facts['serum_creatinine']:g} mg/dL."
                briefing.append(phrase)
            briefing.append("These are follow-up priorities, not diagnoses or mortality probabilities.")
            result.update({
                "capacity": snapshot["capacity"], "selected_count": snapshot["selected_count"],
                "tie_policy": snapshot["tie_policy"],
                "queue": [QueueRow.model_validate(row).model_dump() for row in rows],
                "briefing_text": " ".join(briefing),
            })
        elif name in {"get_patient", "explain_priority"}:
            if not body.patient_id:
                raise DomainError("patient_context_required", "Select a patient first.", 422)
            # Existing typed allowlist excludes time and DEATH_EVENT, even if a
            # future repository starts attaching additional metadata to records.
            patient = PatientRead.model_validate(self.application.patient(body.patient_id, body.snapshot_id)).model_dump()
            result["patient"] = patient
            result["risk_outputs_status"] = "unavailable: supervised models are not connected on this branch"
        else:
            if body.report_id != "case-benchmark-v1":
                raise DomainError("report_not_available", "The requested model report is not available.", 404)
            report = self.application.models()["reports"]["benchmark"]
            result["report_id"] = body.report_id
            # Only the first five examples are needed for a spoken aggregate
            # comparison; never send all 299 movement rows into the conversation.
            result["report"] = {**report, "movements": report.get("movements", [])[:5]}
            result["supervised_status"] = self.application.models()["supervised_status"]
            result["operational_change_applied"] = False
        LOG.info("voice_tool name=%s snapshot=%s patient=%s", name, body.snapshot_id, body.patient_id)
        return result
