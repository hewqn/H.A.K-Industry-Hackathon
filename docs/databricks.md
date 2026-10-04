# Databricks handoff

No workspace is connected or configured by this scaffold. Databricks Free Edition or
restricted event capabilities must be verified first. Copy the capability example to
an ignored local file, fill verified values/evidence, and choose one transport mode.

1. ML/backend jointly verify notebooks, permitted catalog/schema, Delta writes, MLflow,
   SQL warehouse/external credentials, quotas, and optional services. Do not assume a
   service principal, catalog creation, serving, Apps, Foundation Models, or Jobs.
2. Import/open the notebook skeletons. Put the repository on the notebook import path
   or build/install the Python package using a workspace-supported method. Confirm
   compatible pinned dependencies against the actual runtime before model serialization.
3. Review `sql/001_tables.sql` and implement ingestion/publication in approved tables.
   Original row IDs/hash must survive ingest. Features and outcomes stay separate.
4. Run ML protocol, log all candidates and frozen pipeline/report to workspace MLflow,
   score in a bounded notebook, and publish versioned predictions and aggregate reports.
5. Backend implements `repositories/base.py` for SQL or versioned export/import. Tables
   come from a configured allowlist; values use native binding. App must not read raw
   records/outcome tables. Record whether isolation is permissions-enforced or logical.

## Notebook import setup

`hf_followup` is repository code under `src/hf_followup`, not a package that comes with
Jupyter or Databricks. The training notebook's setup cell locates the repository and
adds `src` to `sys.path` before importing it. Run the notebook from this checkout, or
set `REPO_ROOT_OVERRIDE` to the absolute folder containing `src`, `data`, and
`pyproject.toml`. The dataset path is derived from that folder.

If you imported only `02_training.ipynb` into Databricks, also clone/upload the shared
source and dataset. A notebook file alone cannot supply its imported modules. On
serverless, set an explicit absolute repository path because the working directory is
not guaranteed. [Databricks module/import documentation](https://docs.databricks.com/aws/en/files/workspace-modules).

For local experimentation, install the package's ML dependencies into the active
notebook kernel using a separate cell after the setup cell:

```python
%pip install -e "{REPO_ROOT}[ml]"
```

`%pip` installs in the active IPython kernel environment.
[IPython magic documentation](https://ipython.readthedocs.io/en/stable/interactive/magics.html#magic-pip).
Restart the kernel if required and rerun from setup. On Databricks, check installed
runtime/environment packages first and use supported environment settings to supply
compatible missing ML dependencies; avoid blindly replacing its managed environment.

## Publication contract for ML owner

Produce `model_metadata.json` (ID/version/run URI, feature order, source hash, seed,
parameters, software versions, explanation/calibration state); `split_manifest.json`;
`evaluation_report.json` (fold metrics/variation, selected candidate, final test N/K,
baselines, limitations); complete frozen pipeline/signature/input example; compatible
dependency lock. Predictions include patient ID, model version, score kind, actual
attribution scale and development-in-sample versus held-out-test provenance.

The API consumes published predictions; it does not retrain. Managed serving is optional.
Do not choose a winner from full-cohort outcomes or tune after inspecting the test set.
Never load uploaded joblib/pickle artifacts; persistence formats can execute code.

## Durable command implementation for backend owner

One API writer per session. Every mutation supplies command ID and expected session
revision. Lock, look up any prior command, check revision, calculate state/snapshot,
append one complete `application_events` payload, confirm command ID, then acknowledge.
The event includes actor/reason, before/after references and resulting snapshot/state.
Replay rebuilds materialized workflow/history views. Delta does not enforce the proposed
keys; deduplicate command IDs and reject conflicting payloads. Do not rely on atomic
cross-table writes. Handle an ambiguous timeout by checking the command ID before retry.

## Restricted-workspace path and offline fallback

If external SQL/API access is denied, export a checksummed feature/prediction/report
bundle from the notebook; a minimal checksum helper is in `repositories/bundle.py`.
Backend implements a local SQLite cache/outbox. New offline commands are durable
`pending_sync`, never claimed as cloud commits. Export pending command IDs/revisions/
payloads, import in order using the same protocol, and verify notebook receipts before
acknowledging. Stop on remote revision conflict for manual reconciliation; no overwrite.
Checksums detect corruption, not authenticity: only import reviewed team outputs.

Record source/model versions, refresh time, transport mode, actual Delta/MLflow evidence,
one restart recovery, and one reconciliation drill. Local source-code/tests do not
satisfy DB-01/DB-02 until these workspace checks have really happened.

## Implemented local ML handoff

See [ML integration](ml-integration.md). `make train` refits frozen selections,
verifies their lineage and publishes the local prediction bundle. `make publish-models`
promotes notebook artifacts in their training environment. Notebook 03 contains
gated local/Delta publication and version-scoped replaceWhere writes, requiring an
approved Volume readable by Spark. Live writes/MLflow logging remain unverified.
The 897-row JSONL export matches model_predictions; backend transport must preserve
model/threshold/band versions and require complete cohort coverage.
