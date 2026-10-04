# PRD traceability at scaffold handoff

This records implementation starting points, **not** a P0 release certification.

| PRD ID | Current scaffold | Work still required |
|---|---|---|
| DATA-01 | Ingest/checksum/IDs/report + meaningful tests | Actual Databricks ingest evidence and review |
| ML-01 | Runnable CV comparison, frozen choices and exploratory test reports | Fresh validation and actual Databricks evidence |
| ML-02 | Frozen training/inference/publication, versioned cache and reload/checksum/explanation tests | Real MLflow run/signature logging and cloud lineage |
| DB-01 | Table reference/notebooks/capability template | Real Delta/MLflow work in approved workspace |
| DB-02 | Repository interface + connection configuration | Actual transport, durable events/cache/outbox/restart/reconciliation |
| DB-03 | Capability-gated notes | Optional serving/Apps/Jobs/provider services |
| QUEUE-01 | Shared ranking + read-only default queue/evidence | Full UI method/priority behavior and integration QA |
| QUEUE-02 | Queue calculation accepts workflow/overrides | Persistent transitions, search/capacity UI, reasoned mutations, overflow recovery |
| VIZ-01 | Typed anatomy handoff + indicator text cards | Engineer supplies geometry/viewer and actual Three.js integration |
| VIZ-02 | Manifest/lifecycle interface and integration README | Engineer asset/module, camera/resize/disposal/performance/failure tests |
| CMP-01 | Labelled benchmark and frozen supervised reports/selections | Completed comparison UI and fresh validation |
| CMP-02 | Heart-only evaluator with movement/decision | Snapshot previews and explicit operational apply UI |
| SUM-01 | Factual template + digest boundary | Versioned cache, validated provider adapter if available, all-patient preload |
| VOICE-01 | Private signed sessions, scoped read-only tools, SDK controls/transcript, frozen ML evidence and factual fallback | Actual browser microphone/playback/navigation QA; backend equivalent for browser-combined rankings |
| OPS-01 | In-memory snapshot/evidence contracts | Durable immutable events, audit, concurrency, safe exact-snapshot CSV |
| DEMO-01 | Local numerical/read/UI starter | Live scenario, cached text/audio, screenshots, failure drills, backup recording |
| EVAL-01 | Domain/API tests, source/model limitations, architecture | Full PRD acceptance matrix, actual latency/FPS evidence, timed pitch |
| EXT-01/02 | No implementation | Stretch after P0 integration works |

Use PRD §20 for acceptance expectations and §26 for evidence. Update this table as
owners supply verified implementations; do not conflate scaffold tests with live integrations.

Merge verification: 99 Python tests and 21 frontend tests passed; Ruff, TypeScript
and Vite build passed. Coverage includes frozen ML read-cache/voice agreement,
combined configuration, CORS, ranking revision/cache boundaries, merged dashboard
wiring and the real SDK's idle/text lifecycle. No new live provider or cloud tests
were run during merge resolution. Device audio, live Databricks, final 3D and
provider-summary acceptance remain outstanding.
