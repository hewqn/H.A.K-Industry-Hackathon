# Team handoff and remaining implementation

This repository is a **development scaffold**, not a finished P0 product. The PRD is
the source of requirements. Owners should be assigned by the team; no names assumed.
Every API/config placeholder is intentional and described here or beside its code.

Latest ML experiment addition: `02_training.ipynb` and `ml/experiments.py` implement
preprocessor+model pipelines for logistic regression, random forest and gradient boosting,
editable bounded GridSearchCV, held-out reports/confusion matrices at default and
development-OOF-selected classification thresholds,
and three frozen output pipelines. `heart_risk`/`kidney_risk` are organ-feature-associated
recorded-death proxies; `patient_risk` learns from all allowlisted features. Organ-specific
outcome labels are absent. Experimental relative bands use development OOF-score thirds
and differ from PRD queue-priority bands; existing measurement colors remain unchanged.
Results/pipelines are exported locally under ignored `runtime/ml-experiments/`.
The notebook now tunes parameters with positive-class F1, then selects each family by
fewest development OOF false negatives, breaking ties with more true negatives/true
positives, CV AUC, then simpler family. Thresholds remain development-OOF-F1-tuned to
balance precision/recall; FN-only threshold minimization would flag everyone positive.
The development selection table exposes all four confusion counts for every candidate
family. OOF results are conditional on parameter/threshold selection, not independent
validation. `MODEL_SELECTION="cv_metric"` and `REFIT_METRIC="capture_at_k"` restore
PRD queue-based selection. This user-selected classification policy differs from that
queue objective. Inference must apply `predict_proba(...)[:, 1] >= selected_threshold`;
plain pipeline `.predict()` still uses 0.5. Thresholds are provided in
`results["selected_thresholds"]` and each task's `selected_threshold` in the JSON report.
Band boundaries and ranking scores remain separate from the classification threshold.
Repeatedly viewing the same test set makes further comparisons exploratory; fresh
validation is required before claiming a general performance improvement.
The application now consumes a versioned JSON prediction cache and exposes all three
outputs to the patient API/frontend/3D contract. `make train` refits the committed
selections; `make publish-models` promotes existing notebook artifacts. See
[ML integration](ml-integration.md) for scripts, inference and bundle contracts.
Actual MLflow logging, workspace Delta verification and SQL transport remain owner tasks.

## Workstreams

| Owner | Start here | What is already provided | What the owner must implement |
|---|---|---|---|
| ML/data | `ml/training.py`, `databricks/notebooks/02_training.ipynb` | Runnable CV notebook, frozen choices, standalone training/inference/publication, versioned cache/API contracts | Fresh validation, actual Databricks ingest/training/MLflow logs and verified Delta publication |
| Backend/database | `api/main.py`, `services/application.py`, `repositories/base.py`, `databricks/sql/001_tables.sql` | Read-only data slice, request/response schemas, numerical ranking, grounded evidence/indicators, explicit unfinished routes | Repository adapters, Delta/cache transport, event protocol, session revision checks, idempotency, durable snapshots, workflow/overrides, history, summary cache, safe export |
| Frontend/3D | `frontend/src/App.tsx`, `components/AnatomyViewer.tsx`, `anatomy/adapter.ts` | Working local top-25 selection layout, API types, stale-response protection, typed 3D handoff and text cards | Final UI flows, method/capacity/search, comparisons/history, workflow forms, asset/viewer, lifecycle/performance/accessibility QA |
| API integrations (shared) | `.env`, `.env.example`, `docs/api-integrations.md` | Commented settings, planned routes, evidence/tool contracts | Each owner configures and verifies the APIs used by their part; coordinate private voice session/tools and summary provider ownership |

## What runs now

CSV validation → published patient model (or points fallback) → hashed deterministic top 25 → API
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
