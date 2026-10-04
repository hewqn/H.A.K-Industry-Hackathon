# Using the selected models

`configs/ml_selection.json` freezes heart = random forest, kidney = random forest,
patient = logistic regression. It includes parameters, feature order, thresholds,
relative band cutoffs, development counts and the source hash. The thresholds are
approximately 0.517, 0.318 and 0.468.

## Build and run

After `make setup`:

```sh
make train          # Refit the agreed configurations and publish the app cache
make bootstrap      # Refresh patient example and baseline-only inference input
make api            # Load the cache once at startup
make web
```

Training fits the 239 development records and verifies frozen OOF counts/bands.
It reports the 60 test records, without another grid search or model reselection.
Outputs go under `runtime/ml-models/hf-<content-id>/`; `current.json` atomically
activates a complete bundle. Generated pipelines/caches are ignored by Git. A fresh
clone regenerates them from committed selections. The verified pinned refit reproduced
all three notebook scores across all 299 patients within 1e-12.

To promote existing notebook artifacts without refitting, use `make publish-models`
in the library environment that fitted them. If version checks fail, `make train`
refits the frozen choices with the pinned dependencies. Restart the API after
publication: existing snapshots remain version-bound during patient browsing.

`HF_MODEL_BUNDLE_DIR` selects a publication root or immutable bundle; an empty value
disables ML. `HF_DEFAULT_METHOD=auto` uses `patient_risk` when published, otherwise
`points_v1`. Corrupt/stale caches fail loading instead of silently replacing scores.

## Python and batch inference

```python
from pathlib import Path
from hf_followup.ml.inference import RiskPredictor

predictor = RiskPredictor(Path("runtime/ml-models"))
risks = predictor.predict_patient(facts)  # all eleven baseline predictors
heart = risks["heart_risk"]
kidney = risks["kidney_risk"]
patient = risks["patient_risk"]
print(patient["score"], patient["band"], patient["classification_positive"])
```

```sh
.venv/bin/python scripts/predict.py \
  --input contracts/examples/prediction-input.json \
  --output runtime/new-patient-predictions.json
```

Input is `{patient_id: {all eleven baseline values}}`. Missing/nonfinite values,
invalid ranges/binary flags, extra columns, `time` and `DEATH_EVENT` are rejected.
New-record inference always carries `new_patient_inference`, even if an ID matches
a training record. Only verified full-cohort exports use development-in-sample or
held-out-test tags. Inference never fits and checks saved library versions/layout.
Only use trusted team-created joblib files; checksums detect corruption, not authorship.

## Backend, frontend and 3D contract

- `GET /api/v1/models`: frozen selections, feature order, thresholds, versions and
  aggregate reports; `supervised_status` is `ready` or `not_published`.
- Existing patient responses include `model_risks`, containing all three outputs.
- `GET /api/v1/patients/{id}/risks?snapshot_id=...`: the same typed risk envelope.
- Ranking methods `patient_risk`, `heart_risk` and `kidney_risk` use continuous scores
  with the existing tie/capacity policy. Hard classifications do not form the queue.

Each estimate has `score`, relative `band`, `classification_positive`, the actual
threshold, family/version, provenance/calibration and evidence. Apply the threshold
to `predict_proba()[:, 1]`; plain pipeline `.predict()` still uses 0.5. Logistic
evidence is the fitted scaled-feature contribution to log-odds plus the real intercept.
Forest evidence is recorded inputs, explicitly without patient-specific attribution.
Normal API reads consume JSON and do not deserialize or fit models. Patient POST/PUT
lazily load the exact trusted frozen publication and infer all three outputs before
saving. Compatible persisted events replay their risk envelopes without model loading;
legacy or previous-publication events re-score their facts with the current frozen
pipelines. No application interaction fits a model.

Every snapshot row and patient response includes the same `model_risks` envelope.
The dashboard displays all three outputs and passes the independent heart/kidney scores
to the existing `AnatomyViewer`; both kidney meshes share `kidney_risk`. Risk Score uses
these model scores; Tissue State uses EF/creatinine measurement indicators. Relative
bands are separate from both classification thresholds and queue-priority bands.
The engineer owns geometry; left/right-specific targets are absent. The alternate
`anatomy/adapter.ts` is an unused future handoff, not the current rendering path.

The toolbar supports Add patient, confirmed Delete, refresh and selection outside
Top 25. POST/PUT save scored baseline facts; DELETE removes live prediction/workflow
indexes while retaining audit history. See [ML/dashboard audit](ml-dashboard-audit.md)
for the model trace, findings, request lifecycle and verified boundaries.

## Database handoff and remaining work

Bundles contain `model_metadata.json`, three trusted pipelines, `split_manifest.json`,
`evaluation_report.json`, `predictions.json` and `delta_predictions.jsonl`. The latter
matches the existing `model_predictions` schema: 897 rows, or 299 patients × three
models, with thresholds, versions, evidence, source and feature digests in nested JSON.

`databricks/notebooks/03_publish_and_sync.py` supplies local publication and gated
version-scoped Delta writes. Configure a permitted Volume and catalog/schema before
enabling writes. Live workspace behavior has not been verified. These writes are not
atomic across tables: the backend must require a complete bundle with matching versions
rather than independently selecting "latest" rows. SQL/export transport, permissions,
durable events and actual MLflow run/signature logging remain owner work.

Models predict recorded death over observed follow-up. Organ subsets are mortality
proxies, and bands are relative scores, not disease grades. Repeated test-set inspection
makes comparisons exploratory; clinical calibration/independent validation are absent.
