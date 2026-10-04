# ML/dashboard integration audit

Branch: `streamlining_changes`. Scope: trace the committed selections through frozen
artifacts, API ranking, patient details, anatomy, voice retrieval and patient CRUD.
This audit preserves the existing React/FastAPI/repository architecture and model choices.

## Verified model path

`configs/ml_selection.json` → `ml/training.py` → `ml/publishing.py` → checksummed
publication → `repositories/predictions.py` → `services/application.py` → typed
snapshot rows → `frontend/src/api/loadRanking.ts` → dashboard and anatomy.

The local publication is `hf-697f9c3afb96c737aef4`. Re-running its **frozen inference**
on all 299 original records reproduced all 897 outputs exactly: maximum score
difference **0.0**, and all complete risk envelopes matched the published JSON.
This check did not refit or change any model, publication or patient record.

| Output | Selected model | Inputs | Classification threshold | Lower/middle band cutoffs |
|---|---|---|---|---|
| `heart_risk` | Random forest | EF, age, high blood pressure, diabetes, smoking, anaemia | 0.516623019553755 | 0.31922457552064615 / 0.5059261351232341 |
| `kidney_risk` | Random forest | Creatinine, age, recorded sex, diabetes, high blood pressure, smoking | 0.31776478679935855 | 0.3277733408410296 / 0.478298126824106 |
| `patient_risk` | Logistic regression | All eleven baseline features | 0.4683341342643569 | 0.2741200417939404 / 0.5600136759969825 |

Preprocessing is inside each fitted pipeline, using the frozen feature order. Logistic
scaling and any fitted transforms remain unchanged during inference. `time` and
`DEATH_EVENT` are rejected as inference/API inputs and excluded from ordinary patient
and voice reads. Artifacts check checksums, library versions, estimator parameters,
feature order and class order. The default ML queue ranks continuous `patient_risk`
scores; it does not rank class labels or average the three model outputs.

The existing selection policy chooses families by development OOF false negatives,
then true negatives/positives, CV AUC and simpler family. Hyperparameters and thresholds
use development F1. This user-selected policy differs from the PRD's queue-capture
objective; this integration does not silently change that policy or retune the models.

## Findings and fixes

| Finding | Result after this change |
|---|---|
| Add created baseline facts without predictions, breaking ML ranking | All three frozen pipelines score before the durable event is appended. Failed inference leaves the patient and revision unchanged. |
| Edit left old cached predictions attached to new facts | PUT merges baseline facts and recomputes all three outputs before saving. |
| Delete left prediction entries and could reuse the highest patient ID | Live facts, predictions, workflow and overrides are removed together; an event-replayed high-water sequence prevents ID reuse. Audit history is retained. |
| New/edited records could break startup replay | Events store feature digest, bundle ID, full risk envelope and receipt. Compatible outputs replay without deserializing models; legacy or previous-publication facts are scored with the currently loaded frozen pipelines. |
| Retried additions generated a different ID; deletion retries could return 404 | CRUD retries return the original receipt for the same command/request, including after restart. Reusing a command for different input returns 409. |
| A patient read could mix an old snapshot's facts with current global risks | Every snapshot row carries its own copied `model_risks`. Patient reads and voice tools use that same envelope. |
| Logistic score metadata omitted its real intercept | Ranking now reads the intercept from the patient's prediction, matching the published log-odds evidence. |
| Both organs were colored with the overall queue score | Heart receives `heart_risk.score`; both kidney meshes receive `kidney_risk.score`, independently of queue mode. |
| Model scores/bands/provenance were hidden | A three-output panel shows continuous scores, relative bands, classifications, thresholds, versions and actual evidence. |
| Combined ordering displayed only rule points as its score | The displayed combined score now matches `patient_risk.score + points / (heart_weight + 6)`; rule points remain separately visible. Priority bands follow the combined rank. |
| A low-score new patient disappeared outside Top 25 | The eligible-patient picker uses all snapshot rows; the call table still shows only the first 25. |
| Empty API queues fell back to CSV, resurrecting original records | An empty API result stays empty. After a patient action, refresh failures are visible and cannot switch to the original CSV. |
| Patient writes could race ranking commands or spoken evidence | Browser writes/ranking requests serialize; backend session locking and expected revisions protect commits and composite voice reads. |
| Mutation left old voice context usable in the UI | Saving ends/disables the prior context immediately. Refresh obtains a current snapshot; stale server grants return 409. |
| The original benchmark used the changing live cohort count | Benchmark sample size stays 299 and is explicitly labelled as the original points benchmark. |
| Infinite numeric inputs could pass range-only validation | Requests reject nonfinite values and return safe 422 field diagnostics without echoing measurements. |

Risk Score is the user's requested organ-model view. Tissue State retains the PRD's
EF/creatinine measurement indicators. Relative model bands, classification thresholds
and resource-based queue priority bands are distinct: for example, a kidney score can
be in its lower relative band while exceeding its classification threshold.

## Patient actions

1. Start the API and frontend; use **Add patient** in the top toolbar.
2. Enter all six numeric measurements and all five binary fields explicitly. Units
   match the existing dataset contract. No name, contact details, outcomes or follow-up
   duration are requested. The backend assigns the synthetic ID.
3. The API pins inference to the immutable publication loaded at startup. The first
   write lazily loads its trusted pipelines; subsequent writes reuse them. There is
   no fitting, grid search, provider call or Databricks dependency in local inference.
4. A successful command durably records facts and all three risk outputs in the
   configured repository, advances the session revision once, and refreshes the
   default ranking. Original patients retain their original score/provenance.
5. The browser clears ranking caches, reloads the active ordering and selects the new
   patient, even outside Top 25. Delete requires confirmation and an audit reason;
   removal backfills the queue and selects another remaining patient.
6. Transport retries reuse the same command. A revision conflict refreshes read models
   and requires retry; entered form values remain available. Explicit points-only mode
   supports CRUD with rule scores and clearly unavailable ML outputs.

Patient events survive restart in local SQLite or the configured repository. Model
artifacts are immutable and are never rewritten by CRUD. Replaying old events after
publication changes recomputes affected facts with the current frozen models; historical
snapshot commands tagged with another bundle are not exposed as current-version views.
A restart creates a new default snapshot and requires fresh browser/voice context.
Deletion removes a live record, not its immutable audit events or original model artifacts.

## Verification and remaining boundaries

Automated checks cover real frozen predictions, threshold/evidence agreement,
add/edit/delete and receipt retries, SQLite restart replay, legacy records, inference
failure atomicity, concurrent writes without fitting, label/nonfinite rejection, voice
invalidation, independent organ colors, all-row selection, form payloads, confirmation,
failed saves, empty queues, API-only mutation refreshes and fixed benchmark size.
OpenAPI and TypeScript contracts are regenerated from the backend schemas.

Verification passed: **106 Python tests, 34 frontend tests**, Ruff, TypeScript,
production build and whitespace checks. Frontend lint retains the pre-existing
AnatomyViewer effect warning; Vite retains its bundle-size warning. An isolated
in-memory API smoke test against the actual local publication successfully added,
read and deleted a patient with matching three-risk snapshot/patient envelopes.
It left the real patient database and all published artifacts unchanged.

The original data has **no organ-specific outcomes**. All three models predict the
recorded death outcome from different baseline feature sets; they are uncalibrated
proxies without a fixed prediction horizon. They do not establish heart/kidney disease
severity or validated individual mortality probabilities. Existing repeated test-set
inspection remains exploratory. This audit verifies application consistency, not new
clinical validation or improved model discrimination.

Weight 2/3 remain the existing browser-combined ML/points views. They have no equivalent
backend snapshot and therefore retain factual voice fallback. The original pure-points
benchmark is explicitly separate. Browser-combined ordering preserves explicit pins ahead of automatic scores.
Backend methods and eligibility remain authoritative
for API-backed Model/Oldest/points-only modes. The app still requires one API worker per
session; the local lock does not supply multi-process coordination or clinical identity.

Browser automation was unavailable in this session (native computer-use startup failed),
so no visual, microphone or speaker acceptance is claimed. Component tests exercise the
real forms and SDK lifecycle; geometry was not generated or replaced. Live Databricks,
MLflow lineage and full PRD workflows outside these patient/ML changes remain team work.
