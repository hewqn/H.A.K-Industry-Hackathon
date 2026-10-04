# API connection map

The same explanations are in `.env` and the committed `.env.example`. No credentials
are populated. Each workstream implements and verifies its own dependencies.

| Connection | Owner | Configuration | Responsibility / completion check |
|---|---|---|---|
| Frontend → FastAPI | Frontend + backend | Vite proxy in `frontend/vite.config.ts`; allowed origins | Use `/api/v1` and snapshot IDs; test actual Pydantic responses and failed/stale requests |
| API → Databricks SQL/Delta | Backend | Workspace hostname, HTTP path, server credential, catalog/schema | `Repository` methods: bounded features/predictions/reports plus event/summary transport; demonstrate real read/commit/restart |
| Notebook → MLflow | ML | Permitted workspace auth and experiment name | Candidate history, frozen fitted pipeline/signature, split/report/version lineage; actual Databricks run required |
| Browser → ElevenLabs agent | Integrating owner + frontend | `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID` on server | `/voice/session` issues signed WebSocket credentials; React SDK handles microphone, playback, text sessions and transcript |
| ElevenLabs → browser → evidence API | Integrating owner + backend | Seven **client tools**; short-lived snapshot-scoped application token | `/voice/context` provides provider-independent text evidence; `/voice/tools/{name}` validates origin/token/context; two navigation tools update React state; no workflow mutation tools |
| API → summary provider | Integrating owner + backend | Optional structured-output endpoint; provider-specific server key | Digest-grounded factual JSON, bounded timeout/concurrency, fact/numeric validator, retry once then template fallback |
| Optional managed services | Respective owner | Capability-gated serving/Apps/Jobs settings | Stretch after P0 works; no deployment or recurring job is provisioned by the scaffold |

## Planned routes

The schema is discoverable at FastAPI `/docs`; `make types` regenerates frontend types.
Working reads: `/health`, `/cohorts/current`, `/models`, `/ranking-snapshots/{id}`,
`/patients/{id}?snapshot_id=…`. `POST /ranking-snapshots` uses the backend command
protocol and configured repository; `POST /patients/{id}/summary` returns a template after digest validation.
`POST /comparisons/heart-weight` returns the fixed descriptive benchmark.

Workflow, overrides, audited reset, audit events and queue CSV are implemented by
the backend. Voice routes are implemented; missing credentials or provider failures
return safe errors. See [ElevenLabs integration](elevenlabs-integration.md) for setup,
agent configuration, tool definitions, and live verification.

## Voice tool agreement

Implemented read/preview tools: `get_queue` (default 3, maximum 5), `get_patient`,
`explain_priority`, `get_comparison`, `preview_heart_weight`. Client navigation:
`select_patient`, `focus_organ`. Pass explicit patient/snapshot IDs; do not accept URLs,
SQL, arbitrary field lists, code, or outcome-row requests. Override reasons are data,
never prompt instructions. Stop playback on selection changes. Unknown symptoms,
medicines and contacts are unavailable; the agent must say so.

The browser injects the displayed snapshot and rejects contradictory agent arguments.
The API allows only the five read tools with a scoped, expiring token. Selecting a
patient tears down the conversation and transcript; reconnect for the new patient.
Fallback CSV rankings do not have backend snapshot identity, so voice is disabled
there while labelled local factual shortcuts remain available.

## Primary integration references

- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)
- [Databricks SQL Connector, native value binding](https://docs.databricks.com/aws/en/dev-tools/python-sql-connector)
- [ElevenLabs React SDK and client tools](https://elevenlabs.io/docs/eleven-agents/libraries/react)
- [Three.js GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html)
- [scikit-learn StratifiedKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedKFold.html)

These are wiring references; confirm compatibility with the team's permitted workspace
and the SDK versions chosen when implementing live integrations. AWS doc links do not
establish which cloud hosts the actual workspace.
