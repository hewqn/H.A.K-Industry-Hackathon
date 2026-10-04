"""Check that agent setup changes integration settings, not the owner's prompt/voice."""

import copy
import importlib.util
from pathlib import Path

import httpx

from hf_followup.config import ROOT, Settings

SPEC = importlib.util.spec_from_file_location("voice_setup", ROOT / "scripts/configure_voice_agent.py")
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


def test_configuration_preserves_owner_settings_and_attaches_only_client_tools(tmp_path):
    original = {
        "conversation_config": {
            "agent": {"prompt": {"prompt": "owner prompt", "llm": "owner model", "tool_ids": []}},
            "tts": {"voice_id": "owner voice"},
            "conversation": {"client_events": ["audio"], "max_duration_seconds": 600},
        },
        "platform_settings": {"auth": {"enable_auth": False}, "overrides": {"custom_llm_extra_body": False}},
    }
    agent = copy.deepcopy(original)
    created = []
    patch_body = None

    def handle(request):
        nonlocal patch_body
        import json

        if request.method == "GET":
            return httpx.Response(200, json=agent)
        body = json.loads(request.content)
        if request.method == "POST":
            created.append(body["tool_config"])
            return httpx.Response(200, json={"id": f"tool-{len(created)}"})
        patch_body = body
        return httpx.Response(200, json=agent)

    settings = Settings(root=Path(tmp_path), elevenlabs_api_key="test-key", elevenlabs_agent_id="test-agent")
    with httpx.Client(base_url="https://api.elevenlabs.io/v1", transport=httpx.MockTransport(handle)) as client:
        assert SETUP.configure(client, settings, apply=True)
    assert agent == original  # The adapter never mutates the fetched configuration.
    assert len(created) == 7
    assert all(item["type"] == "client" and item["expects_response"] for item in created)
    assert {item["name"] for item in created} == {"get_queue", "get_patient", "explain_priority", "get_comparison", "preview_heart_weight", "select_patient", "focus_organ"}
    assert "prompt" not in patch_body["conversation_config"]["agent"]["prompt"]
    assert "tts" not in patch_body["conversation_config"]
    assert patch_body["platform_settings"]["auth"] == {"enable_auth": True, "allowlist": []}
    assert patch_body["conversation_config"]["conversation"]["max_duration_seconds"] == 300
    assert list((tmp_path / "runtime/voice-agent-backups").glob("*.json"))
