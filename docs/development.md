# Team handoff and remaining implementation

This repository is a **development scaffold**, not a finished P0 product. The PRD is
the source of requirements. Owners should be assigned by the team; no names assumed.
Every API/config placeholder is intentional and described here or beside its code.

## Workstreams

| Owner | Start here | What is already provided | What the owner must implement |
|---|---|---|---|
| ML/data | `ml/training.py`, `databricks/notebooks/02_training.ipynb` | Feature allowlist, fixed split, scaler/estimator pipelines, CV constructor, baseline evaluator | Actual Databricks ingest/training, bounded candidate evaluation, fold reports, frozen winner/test, MLflow logs, prediction + artifact publication |
| Backend/database | `api/main.py`, `services/application.py`, `repositories/base.py`, `databricks/sql/001_tables.sql` | Read-only data slice, request/response schemas, numerical ranking, grounded evidence/indicators, explicit unfinished routes | Repository adapters, Delta/cache transport, event protocol, session revision checks, idempotency, durable snapshots, workflow/overrides, history, summary cache, safe export |
| Frontend/3D | `frontend/src/App.tsx`, `components/AnatomyViewer.tsx`, `anatomy/adapter.ts` | Working local top-25 selection layout, API types, stale-response protection, typed 3D handoff and text cards | Final UI flows, method/capacity/search, comparisons/history, workflow forms, asset/viewer, lifecycle/performance/accessibility QA |
| API integrations (shared) | `.env`, `.env.example`, `docs/api-integrations.md` | Commented settings, planned routes, evidence/tool contracts | Each owner configures and verifies the APIs used by their part; coordinate private voice session/tools and summary provider ownership |

## What runs now

CSV validation → independent points calculation → hashed deterministic top 25 → API
patient evidence → frontend selection → textual organ indicators and factual overview.
The benchmark confirms 18/21/19 historical outcomes for age/baseline/revision, overlap
22/25, and rejects the revision. These are descriptive case results, not trained ML.

In-memory snapshots disappear on restart. The service does not persist states, train
models, connect to Databricks or ElevenLabs, or render an anatomy model. Workflow,
override, audit, export, and voice route placeholders return `503 integration_pending`.
The ranking function accepts workflow/override input for the backend owner to wire;
that calculation interface does not constitute durable workflow implementation.

## Implementation order

1. Agree contracts: source IDs, feature allowlist, tie/indicator versions, read model,
   repository and anatomy interfaces. Inspect `contracts/examples/patient.json`.
2. ML/backend verify workspace capabilities together; record `capabilities.example.json`
   as a local capabilities file with evidence, without credentials. Choose live SQL or
   restricted export/import. Do not assume serving, Apps, Jobs, or enterprise identity.
3. Backend implement the event protocol before enabling mutation controls. Preserve
   method rank versus adjusted call rank; enforce pin capacity and allowed transitions.
4. ML run the fixed protocol in Databricks and publish frozen reports/predictions. The
   API loads published versions and never retrains during a nurse interaction.
5. Frontend wire completed endpoints; 3D engineer supplies geometry/viewer through the
   existing interface. Keep the same patient/snapshot/digest across every panel.
6. Integrating owners configure ElevenLabs tools/session and optional summary provider.
   Test exact-record retrieval, networking/authentication, transcripts, and failure paths.
7. Run the PRD §20 release matrix. Record real results; scaffold tests are not P0 proof.

## Important invariants for owners

- Only EF weight changes in the heart experiment. Kidney weight remains 2.
- Ties use SHA-256 of `patient-{original_one_based_row}`, then patient ID.
- Benchmark cohort ignores contact statuses and overrides; operational queue backfills.
- Pending → reviewed → contacted; clinician-review resolution and reopening need reasons.
- Pin/defer/reset need reasons; contacted patients must reopen before pinning; reject
  capacity below active pins. Pins come first in creation order, preserving model rank.
- A command has an idempotency key + expected **session** revision; one API writer.
  Append a complete immutable event/snapshot and confirm its command ID before commit.
- Offline writes are `pending_sync`; replay once in order and stop on remote conflict.
- Summaries refer to exact evidence digest/prompt/generator versions; reject unsupported
  facts, wrong numbers/IDs, and outdated context. Template fallback stays available.
- The agent reads/previews/navigates; it does not mutate workflow in P0.
- Outcomes/time never appear in prediction inputs or ordinary patient/voice payloads.

## Empty files and intentionally unset values

There are no unexplained empty source files. Package `__init__.py` files contain
boundary docstrings. `manifest.json` has `asset_url: null` until the engineer supplies
an asset **and** implements the adapter; no models are created by this scaffold.
Provider environment values are blank until configured by their owners. Capability
fields stay `unverified` until someone records a real workspace test. Databricks notebook
TODO cells explicitly list their inputs, outputs, and completion evidence. Generated
dependencies/builds/caches/model binaries are excluded from the handoff.

## Required integration checks still pending

Actual Delta and MLflow runs; frozen artifact reload; backend event persistence/restart
and reconciliation; status/backfill and override flows; final Three.js lifecycle/FPS;
live voice tool trace + transcript; provider summary grounding; exact-snapshot safe CSV;
stale-selection/failure drills; demo screenshots/recording/pitch. See PRD §20/26 for the
full P0 gate. Do not mark these complete because the files or route names exist.
