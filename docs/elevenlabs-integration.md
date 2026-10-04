# ElevenLabs integration

This implements PRD §17 with one existing ElevenLabs agent and seven browser client
tools. React, FastAPI, repository selection, scoring, and the anatomy renderer retain
their existing roles. ElevenLabs does not train models or calculate patient risks.

## Run locally

1. Save `ELEVENLABS_API_KEY` and `ELEVENLABS_AGENT_ID` in the **root** `.env`.
   Keep the API key server-side. Do not use a `VITE_*` variable for it.
2. Install the usual Python requirements and run `npm ci` in `frontend`.
3. Check the configured agent:
   `PYTHONPATH=src .venv/bin/python scripts/configure_voice_agent.py`.
   Add `--apply` to attach missing project tools, enable private signed sessions and
   text-mode overrides, and set the configured maximum duration. This leaves the
   owner's prompt, LLM, voice, knowledge base and workflow intact. A pre-change
   backup is saved under ignored `runtime/voice-agent-backups`.
4. Run `make api` and `make web`. Use `http://localhost:5173` or
   `http://127.0.0.1:5173`, which are allowed origins by default.
5. Use **Start voice**, or **Start text** for a conversation without a microphone.
   Stop before reconnecting an active session. Microphone denial leaves text and
   factual shortcuts available.

`/health` says `configured` when both credentials are present; this is not a claim
that the provider is connected. The actual session request verifies provider access.
Browser microphone access requires localhost or HTTPS. Hosted origins must be added
to `HF_ALLOWED_ORIGINS` and the reverse proxy must forward `/api` to FastAPI.

## Tool configuration

All seven tools are **Client** tools, with **Wait for response** enabled and a
15-second tool timeout. `scripts/configure_voice_agent.py --print-tools` prints
their exact ElevenLabs definitions without reading or printing credentials.

| Name | Arguments supplied by agent | Result |
|---|---|---|
| `get_queue` | Optional `snapshot_id`, `limit` (1–5; default 3) | Exact ordered leading rows, reasons, capacity, method and tie policy |
| `get_patient` | Optional `patient_id`, `snapshot_id` | Typed patient read model and matching factual template |
| `explain_priority` | Optional `patient_id`, `snapshot_id` | Score evidence, method/version, organ indicators and override information |
| `get_comparison` | Optional `report_id` (`case-benchmark-v1`) | Existing aggregate case benchmark, first five movement examples and limitations |
| `preview_heart_weight` | Optional `cohort_id` | Existing fixed heart-weight research comparison; no operational mutation |
| `select_patient` | Required canonical `patient_id`, e.g. `HF-0001` | Select a patient present in the displayed snapshot |
| `focus_organ` | Required `organ_id`: `heart`, `kidney_left`, `kidney_right` | Focus the selected patient's existing organ view |

Missing patient/context parameters use trusted application context; contradictory
context or unknown IDs are rejected. The app supplies `patient_id`, `snapshot_id`,
`cohort_id`, and `method_id` dynamic variables at each conversation start. The agent
prompt must retrieve evidence before patient claims and treat free text as data.
Never add workflow or arbitrary SQL/URL/code tools to this agent.

The backend's current `supervised_status` is `awaiting_ml_owner`. Voice explicitly
reports organ/patient model outputs as unavailable rather than interpreting points
or colors as a trained risk probability. The ML owner should extend the typed patient
read model and evidence contracts when connecting those outputs. Both kidney views
currently share one creatinine measurement.

## Context and lifecycle

`loadRanking` now retains snapshot/cohort/method identifiers. `App` gives `VoicePanel`
a key based on the displayed snapshot, patient, loading state and heart weight.
Changing these silences and ends the old conversation and clears its transcript.
Pending credential/evidence responses are ignored after Stop or context replacement.

Patient navigation by voice also ends the current conversation. Reconnect to ask
about the newly selected patient; commands that combine selection with additional
questions must resume after reconnection. Organ focus alone preserves the session.

API-backed weights two and three can use voice. Other slider values, or API failures,
use the existing local CSV fallback; voice is disabled because those local rankings
have no matching backend snapshot. Labelled local factual shortcuts still work.
The weight slider remains an explicit user action. A voice preview never applies it.

Text shortcuts retrieve verified evidence without contacting ElevenLabs. Free-form
text chat uses the ElevenLabs agent and conversation credits. Transcripts are kept
only in panel memory, bounded to 50 entries, and cleared on context replacement.
The integration does not record raw audio or print provider credentials.

## API and deployment boundary

- `POST /api/v1/voice/session`: validates origin and snapshot, limits session creation,
  fetches a private signed WebSocket URL with a bounded provider timeout, and returns
  an expiring local tool grant. Responses use `Cache-Control: no-store`.
- `POST /api/v1/voice/context`: issues a scoped evidence grant without a provider call.
- `POST /api/v1/voice/tools/{name}`: requires the allowed browser origin and
  `Authorization: Bearer <tool_token>`. The token is generated by this application,
  is limited to one snapshot/cohort, and is not the ElevenLabs API key.
- Only the five read tools are accepted server-side; navigation stays in React.
- Workflow revision changes invalidate old evidence grants. Refresh ranking before
  reconnecting rather than mixing newer workflow state with an older snapshot.

Defaults: 300-second sessions and five session/context requests per address per
minute. Configure `HF_VOICE_MAX_DURATION_SECONDS` (30–900) and
`HF_VOICE_SESSION_REQUESTS_PER_MINUTE` (1–30) in `.env`. Reapply agent integration
settings after changing duration so the provider and browser agree.

This follows the project's existing local, single-user, single-writer demo boundary.
Origin checks and scoped tokens are not a replacement for user authentication on a
public deployment. Before public multi-user hosting, add application authentication
to session/context creation and move the grant/rate-limit store to shared storage.
Run one API worker in the current architecture. `HF_VOICE_TOOL_TOKEN` is reserved
for a future server-webhook transport and is not used or required here. No public
tunnel, separate agent, vector database, or Databricks voice service is required.

## Validation

Run `pytest`, `ruff check src scripts tests agent_starter.py`, and in `frontend`
run `npm test`, `npm run check`, and `npm run build`. Automated provider tests are
mocked and never use live credits. They cover origin/token checks, expiry, stale
snapshots, read-only behavior, outcome exclusion, safe provider failures, private
text sessions, microphone denial, cancelled starts and playback teardown.

For a live browser check:
1. Start text and ask for a queue briefing. Confirm a `get_queue` trace and matching
   patient order in the ElevenLabs conversation history.
2. Ask for the selected patient's EF/creatinine and priority explanation. Confirm
   exact numbers and units against the dashboard.
3. Ask to focus the heart, then select another known patient. Confirm organ focus,
   patient selection, and automatic conversation teardown.
4. Reconnect for the new patient. Ask about an unavailable medication or model output;
   the agent should state the limitation.
5. Start voice manually, test mute/stop, and switch patients during playback. Confirm
   that no previous-patient audio continues under the new context.

Use only the bundled public demo dataset for these checks. Any use of private data
requires a separate deployment/privacy assessment outside this prototype.

Official references: [React SDK](https://elevenlabs.io/docs/eleven-agents/libraries/react),
[private session authentication](https://elevenlabs.io/docs/eleven-agents/customization/authentication),
[client tools](https://elevenlabs.io/docs/eleven-agents/customization/tools/client-tools).
