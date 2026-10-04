"""Voice boundaries: real application evidence, mocked provider, no live credits."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from admin_client import AdminClient

from hf_followup.api.main import create_app
from hf_followup.config import Settings

ORIGIN = "http://localhost:5173"


def forbidden_keys(value):
    if isinstance(value, dict):
        assert not {"DEATH_EVENT", "time"} & set(value)
        for child in value.values():
            forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            forbidden_keys(child)


@pytest.fixture
def client():
    settings = Settings(elevenlabs_api_key="secret-test-key", elevenlabs_agent_id="test-agent")
    with patch("hf_followup.api.main._create_repository", return_value=(None, "in_memory")):
        with AdminClient(create_app(settings)) as client:
            client.headers["origin"] = ORIGIN
            yield client


def context(client, patient="HF-0001"):
    snapshot_id = client.get("/api/v1/cohorts/current").json()["current_snapshot_id"]
    body = {"snapshot_id": snapshot_id, "patient_id": patient}
    response = client.post("/api/v1/voice/context", json=body)
    assert response.status_code == 200
    return body, response.json()


def tool(client, name, body, grant, **kwargs):
    return client.post(
        f"/api/v1/voice/tools/{name}",
        json={**body, "cohort_id": grant["cohort_id"], **kwargs},
        headers={"Authorization": f"Bearer {grant['tool_token']}"},
    )


def test_private_session_uses_server_key_and_no_cache(client):
    body, _ = context(client)
    get = AsyncMock(return_value=httpx.Response(200, json={"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?token=example"}))
    with patch.object(client.app.state.voice.client, "get", get):
        response = client.post("/api/v1/voice/session", json={**body, "text_only": True})
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_id"] == body["snapshot_id"]
    assert data["text_only"] is True
    assert data["connection_type"] == "websocket"
    assert data["tool_token"]
    assert data["max_duration_seconds"] == 300
    assert response.headers["cache-control"] == "no-store"
    assert "secret-test-key" not in response.text
    assert get.call_args.kwargs["headers"] == {"xi-api-key": "secret-test-key"}


@pytest.mark.parametrize("status,code", [(401, "voice_provider_auth"), (403, "voice_provider_auth"), (429, "voice_provider_limit"), (500, "voice_provider_unavailable")])
def test_provider_errors_are_sanitized(client, status, code):
    body, _ = context(client)
    with patch.object(client.app.state.voice.client, "get", AsyncMock(return_value=httpx.Response(status, text="secret-provider-body"))):
        response = client.post("/api/v1/voice/session", json=body)
    assert response.status_code == 503
    assert response.json()["code"] == code
    assert "secret-provider-body" not in response.text


def test_network_timeout_and_bad_signed_url(client):
    body, _ = context(client)
    with patch.object(client.app.state.voice.client, "get", AsyncMock(side_effect=httpx.ReadTimeout("secret-url"))):
        response = client.post("/api/v1/voice/session", json=body)
    assert response.json()["code"] == "voice_provider_unavailable"
    assert "secret-url" not in response.text
    with patch.object(client.app.state.voice.client, "get", AsyncMock(return_value=httpx.Response(200, json={"signed_url": "wss://other.example"}))):
        assert client.post("/api/v1/voice/session", json=body).status_code == 502


def test_unconfigured_provider_does_not_disable_text_evidence(client):
    client.app.state.voice.settings = Settings()
    body, grant = context(client)
    assert client.post("/api/v1/voice/session", json=body).json()["code"] == "voice_unconfigured"
    assert tool(client, "get_patient", body, grant).status_code == 200


def test_read_tools_match_snapshot_and_never_mutate(client):
    body, grant = context(client)
    snapshot = client.get(f"/api/v1/ranking-snapshots/{body['snapshot_id']}").json()
    before = client.get("/api/v1/cohorts/current").json()
    for name in ("get_queue", "get_patient", "explain_priority", "get_comparison", "preview_heart_weight"):
        response = tool(client, name, body, grant)
        assert response.status_code == 200, response.text
        value = response.json()
        forbidden_keys(value)
        assert value["snapshot_id"] == body["snapshot_id"]
        if name == "get_queue":
            assert [row["patient_id"] for row in value["queue"]] == [row["patient_id"] for row in snapshot["queue"][:3]]
            assert len(value["briefing_text"].split()) <= 100
        elif name == "get_patient":
            read = client.get("/api/v1/patients/HF-0001", params={"snapshot_id": body["snapshot_id"]}).json()
            assert value["patient"] == read
            assert value["risk_outputs_status"] == "not_published"
        elif name == "preview_heart_weight":
            assert value["operational_change_applied"] is False
    assert client.get("/api/v1/cohorts/current").json() == before


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_cors_keeps_patient_mutations_and_voice_authorization(client, method):
    response = client.options(
        "/api/v1/patients/HF-0001",
        headers={
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert method in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_tool_auth_allowlist_context_and_argument_validation(client):
    body, grant = context(client)
    assert client.post("/api/v1/voice/tools/get_patient", json=body).status_code == 401
    assert tool(client, "workflow", body, grant).status_code == 403
    assert tool(client, "select_patient", body, grant).status_code == 403
    assert tool(client, "get_patient", {**body, "patient_id": "HF-9999"}, grant).status_code == 404
    assert tool(client, "get_queue", body, grant, limit=6).status_code == 422
    assert tool(client, "get_queue", body, grant, limit=True).status_code == 422
    assert tool(client, "get_patient", body, grant, sql="SELECT * FROM outcomes").status_code == 422
    assert tool(client, "get_comparison", body, grant, report_id="unknown").status_code == 404
    assert tool(client, "get_queue", {**body, "snapshot_id": "other"}, grant).status_code == 409
    assert tool(client, "get_queue", body, grant, cohort_id="other").status_code == 409
    client.app.state.voice._grants[grant["tool_token"]]["expires_at"] = time.time() - 1
    assert tool(client, "get_queue", body, grant).status_code == 401


def test_origin_rejection_and_rate_limit(client):
    snapshot_id = client.get("/api/v1/cohorts/current").json()["current_snapshot_id"]
    body = {"snapshot_id": snapshot_id}
    assert client.post("/api/v1/voice/context", json=body, headers={"origin": "https://other.example"}).status_code == 403
    del client.headers["origin"]
    assert client.post("/api/v1/voice/context", json=body).status_code == 403
    client.headers["origin"] = ORIGIN
    for _ in range(5):
        assert client.post("/api/v1/voice/context", json=body).status_code == 200
    assert client.post("/api/v1/voice/context", json=body).status_code == 429


def test_workflow_change_invalidates_old_voice_context(client):
    body, grant = context(client)
    response = client.patch("/api/v1/patients/HF-0001/workflow", json={"command_id": "voice-test-command", "expected_revision": 0, "state": "reviewed"})
    assert response.status_code == 200
    assert tool(client, "get_patient", body, grant).json()["code"] == "stale_voice_context"
