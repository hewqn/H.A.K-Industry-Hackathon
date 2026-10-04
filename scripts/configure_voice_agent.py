"""Check/configure only the integration settings of the existing ElevenLabs agent.

Default is read-only. --apply attaches our seven client tools, enables private
signed sessions and text mode, and bounds duration. Prompt, LLM, voice, knowledge
base and workflow stay as configured by the owner. Existing settings are backed
up under ignored runtime/ before a remote change. No key is printed or persisted.

Run with PYTHONPATH=src python scripts/configure_voice_agent.py [--apply].
--print-tools prints the exact tool definitions for manual dashboard setup.
"""

import argparse
import copy
import json
from datetime import UTC, datetime

import httpx

from hf_followup.config import Settings

PATIENT = {"type": "string", "description": "Canonical patient ID such as HF-0001. Use a known patient in the active snapshot; omit to use the current selection."}
SNAPSHOT = {"type": "string", "description": "Exact active snapshot_id from application context. Never invent an ID; omit to use the application's trusted active snapshot."}
COHORT = {"type": "string", "description": "Exact active cohort_id from application context. Omit to use the application's trusted cohort."}


def tool(name, description, properties=None, required=None):
    return {
        "type": "client", "name": name, "description": description,
        "expects_response": True, "response_timeout_secs": 15,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }


TOOLS = [
    tool("get_queue", "Retrieve the current ordered follow-up queue before briefing it. Read the returned briefing_text for the initial 20–40 second briefing without additional rank/measurement recitation. Preserve returned order, explain at most five patients, and never mutate the queue.", {"snapshot_id": SNAPSHOT, "limit": {"type": "integer", "description": "Number of patients, one to five. Default three."}}),
    tool("get_patient", "Retrieve exact recorded patient facts and the factual summary before stating patient information. Missing model outputs must be described as unavailable.", {"patient_id": PATIENT, "snapshot_id": SNAPSHOT}),
    tool("explain_priority", "Retrieve backend score evidence, rank, method, overrides, and limitations before explaining why a patient is prioritized. Evidence is not clinical causality.", {"patient_id": PATIENT, "snapshot_id": SNAPSHOT}),
    tool("get_comparison", "Retrieve the aggregate case benchmark. This branch has no supervised-model evaluation report; never invent a winning trained model.", {"report_id": {"type": "string", "description": "Only case-benchmark-v1 is available. Omit to use it."}}),
    tool("preview_heart_weight", "Retrieve the fixed descriptive comparison of heart weights two and three. This is a research preview and never applies an operational ranking change.", {"cohort_id": COHORT}),
    tool("select_patient", "Select a known patient in the displayed snapshot. Selection stops the current conversation to prevent old-patient playback; reconnect for the selected patient. Never claim selection before success.", {"patient_id": PATIENT}, ["patient_id"]),
    tool("focus_organ", "Focus the selected patient's existing anatomy view. Only heart, kidney_left, or kidney_right are permitted. Both kidneys share one recorded creatinine measurement.", {"organ_id": {"type": "string", "enum": ["heart", "kidney_left", "kidney_right"], "description": "Exact organ identifier: heart, kidney_left, or kidney_right."}}, ["organ_id"]),
]


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.is_error:
        # Do not print raw bodies, URLs, headers, or exception strings containing
        # server credentials. Status and operation are sufficient for diagnosis.
        raise RuntimeError(f"ElevenLabs {method} request failed (HTTP {response.status_code}). Check API-key permissions and agent ownership.")
    return response.json()


def configure(client, settings, apply=False):
    path = f"/convai/agents/{settings.elevenlabs_agent_id}"
    agent = request(client, "GET", path)
    conversation = agent["conversation_config"]
    prompt = conversation["agent"].get("prompt", {})
    existing = {}
    for identifier in prompt.get("tool_ids", []):
        item = request(client, "GET", f"/convai/tools/{identifier}")
        existing[item["tool_config"]["name"]] = item
    for item in prompt.get("tools", []):
        existing.setdefault(item["name"], {"tool_config": item})
    missing = [item["name"] for item in TOOLS if item["name"] not in existing]
    incompatible = [item["name"] for item in TOOLS if item["name"] in existing and (existing[item["name"]]["tool_config"].get("type") != "client" or not existing[item["name"]]["tool_config"].get("expects_response"))]
    platform = agent.get("platform_settings", {})
    private = platform.get("auth", {}).get("enable_auth", False)
    print("Missing client tools:", ", ".join(missing) or "none")
    print("Incompatible client tools:", ", ".join(incompatible) or "none")
    print("Private signed-session authentication:", "enabled" if private else "disabled")
    if not apply:
        return not missing and not incompatible and private
    if incompatible:
        raise RuntimeError("Existing tools conflict with this integration. Review those tools in the dashboard before applying.")

    backup = settings.root / "runtime" / "voice-agent-backups"
    backup.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    (backup / f"{stamp}.json").write_text(json.dumps({"conversation_config": conversation, "platform_settings": platform}, indent=2) + "\n")
    identifiers = list(prompt.get("tool_ids", []))
    for definition in TOOLS:
        if definition["name"] in existing:
            item = existing[definition["name"]]
            if item.get("id") and any(item["tool_config"].get(key) != value for key, value in definition.items()):
                request(client, "PATCH", f"/convai/tools/{item['id']}", json={"tool_config": definition})
                print("Updated client tool:", definition["name"])
            continue
        created = request(client, "POST", "/convai/tools", json={"tool_config": definition})
        identifiers.append(created["id"])
        print("Created client tool:", definition["name"])

    overrides = copy.deepcopy(platform.get("overrides", {}))
    overrides.setdefault("conversation_config_override", {}).setdefault("conversation", {})["text_only"] = True
    events = list(dict.fromkeys([*conversation.get("conversation", {}).get("client_events", []), "audio", "interruption", "user_transcript", "agent_response", "agent_response_correction"]))
    request(client, "PATCH", path, json={
        "conversation_config": {
            "agent": {"prompt": {"tool_ids": identifiers}},
            "conversation": {"max_duration_seconds": settings.voice_max_duration_seconds, "client_events": events},
        },
        "platform_settings": {"auth": {"enable_auth": True, "allowlist": []}, "overrides": overrides},
    })
    print("Attached client tools; enabled private sessions and text mode; set duration limit.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--print-tools", action="store_true")
    args = parser.parse_args()
    if args.print_tools:
        print(json.dumps(TOOLS, indent=2))
        return 0
    settings = Settings.from_env()
    if not settings.elevenlabs_api_key or not settings.elevenlabs_agent_id:
        print("Set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID in the root .env.")
        return 1
    try:
        with httpx.Client(base_url="https://api.elevenlabs.io/v1", headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=15) as client:
            return 0 if configure(client, settings, args.apply) else 1
    except (httpx.RequestError, RuntimeError):
        print("Agent configuration failed. Check connectivity, API-key permissions, and tool compatibility. No secrets were printed; a pre-change backup is retained if apply began.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
