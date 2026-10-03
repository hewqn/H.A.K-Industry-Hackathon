# Heart-failure follow-up — development scaffold

A compact starting repository for the team's **ML**, **backend/database**, and
**frontend/3D** workstreams. The [PRD](docs/heart-failure-follow-up-prd.md) governs the
build. This is not the completed product; each owner implements their integrations.
The original case brief is preserved in [docs/case-brief.md](docs/case-brief.md).

## Start locally

Use Python 3.11+ and Node 22.12+ (or a compatible newer Node). From the repository root:

```sh
make setup
make bootstrap     # Validate data, reproduce benchmark, refresh safe patient example
make api           # Terminal 1: http://127.0.0.1:8000/docs
make web           # Terminal 2: http://127.0.0.1:5173
```

`make setup` creates local dependency directories; they are ignored by Git and are
not included in this handoff. No provider credentials are needed for the local slice.
`.env` has commented connection instructions and blank credentials; `.env.example`
is its committed template. Copy `.env.example` to `.env` when cloning the repository.

Other entry commands: `make train` prepares the ML split and candidate constructors
without fitting a model; `make types` regenerates OpenAPI/frontend contracts;
`make check` runs Python lint/tests and the TypeScript/production-build checks.

## Provided starting work

- Validated CSV ingestion with stable source-row IDs, checksum, quarantine/reporting,
  separate missing-row/cell counts, and an explicit predictor allowlist.
- Shared points/age ranking, heart-only revision, deterministic ties, queue calculation,
  organ indicators, and descriptive benchmark (18/21/19 outcomes; overlap 22/25).
- Read-only FastAPI data slice and typed patient/evidence/snapshot contracts.
- Small React queue/selection layout with stale-response checks and factual summaries.
- **No generated 3D models.** Typed viewer/asset handoff and usable text cards for the
  engineer; the rendering adapter is intentionally left for them to implement.
- ML split/pipeline constructors, notebook skeletons, Delta table reference, repository
  interface, API wiring TODOs, and owner handoff notes.

Snapshots are in memory and disappear on restart. Workflow, override, audit, export,
voice, Databricks, fitted ML, and provider-summary integrations remain unfinished.
Their routes fail explicitly until implemented; a file or route does not claim completion.

## Where each owner starts

| Workstream | Entry files | Handoff |
|---|---|---|
| ML/data | `src/hf_followup/ml/training.py`, `databricks/notebooks/02_training.ipynb` | [Databricks protocol](docs/databricks.md) |
| Backend/database | `src/hf_followup/api/main.py`, `repositories/base.py`, `databricks/sql/001_tables.sql` | [Architecture](docs/architecture.md), [development responsibilities](docs/development.md) |
| Frontend/3D | `frontend/src/App.tsx`, `components/AnatomyViewer.tsx`, `anatomy/adapter.ts` | [3D asset/viewer contract](frontend/public/assets/anatomy/README.md) |
| API integrations (each owner) | `.env.example`, planned `/api/v1` routes | [Connection map](docs/api-integrations.md) |

Repository layout:

```text
src/hf_followup/      Shared Python domain, ingest, API, ML and storage boundaries
frontend/            React/TypeScript starter and engineer-owned anatomy interface
contracts/           OpenAPI, generated frontend types and safe patient example
scripts/             Local validation, split preparation and schema export entry points
databricks/          Notebook skeletons, capabilities template and Delta table reference
tests/               Implemented numerical/schema/API boundary checks
docs/                PRD, case brief, architecture and team handoff
```

[Development notes](docs/development.md) identify what every unfinished interface needs
to do. [Data notes](data/README.md) record source/license, hash, identity and exclusions.
`DEATH_EVENT` and `time` remain evaluator/trainer-only. Historical ranking does not
establish diagnoses, treatment recommendations, or a clinical benefit from calls.
