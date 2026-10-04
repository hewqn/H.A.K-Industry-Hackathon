# PRD traceability at scaffold handoff

This records implementation starting points, **not** a P0 release certification.

| PRD ID | Current scaffold | Work still required |
|---|---|---|
| DATA-01 | Ingest/checksum/IDs/report + meaningful tests | Actual Databricks ingest evidence and review |
| ML-01 | Split/candidate/CV constructors + notebook skeleton | Bounded CV comparison and final frozen test |
| ML-02 | Artifact fields documented | MLflow runs, fitted pipeline/signature/export, reload checks, dependency lineage |
| DB-01 | Table reference/notebooks/capability template | Real Delta/MLflow work in approved workspace |
| DB-02 | Repository interface + connection configuration | Actual transport, durable events/cache/outbox/restart/reconciliation |
| DB-03 | Capability-gated notes | Optional serving/Apps/Jobs/provider services |
| QUEUE-01 | Shared ranking + read-only default queue/evidence | Full UI method/priority behavior and integration QA |
| QUEUE-02 | Queue calculation accepts workflow/overrides | Persistent transitions, search/capacity UI, reasoned mutations, overflow recovery |
| VIZ-01 | Typed anatomy handoff + indicator text cards | Engineer supplies geometry/viewer and actual Three.js integration |
| VIZ-02 | Manifest/lifecycle interface and integration README | Engineer asset/module, camera/resize/disposal/performance/failure tests |
| CMP-01 | Labelled descriptive benchmark | Supervised CV/test reports and completed comparison UI |
| CMP-02 | Heart-only evaluator with movement/decision | Snapshot previews and explicit operational apply UI |
| SUM-01 | Factual template + digest boundary | Versioned cache, validated provider adapter if available, all-patient preload |
| VOICE-01 | Planned session/tool routes + connection map | Private agent, tool transport/auth, SDK controls/transcript, real Q&A traces |
| OPS-01 | In-memory snapshot/evidence contracts | Durable immutable events, audit, concurrency, safe exact-snapshot CSV |
| DEMO-01 | Local numerical/read/UI starter | Live scenario, cached text/audio, screenshots, failure drills, backup recording |
| EVAL-01 | Domain/API tests, source/model limitations, architecture | Full PRD acceptance matrix, actual latency/FPS evidence, timed pitch |
| EXT-01/02 | No implementation | Stretch after P0 integration works |

Use PRD §20 for acceptance expectations and §26 for evidence. Update this table as
owners supply verified implementations; do not conflate scaffold tests with live integrations.

Scaffold verification on this handoff: 12 Python tests passed; Ruff passed; TypeScript
check and Vite production build passed; notebook cell/config syntax validated. No live
Databricks, voice, final 3D, persistence, or provider-summary acceptance is claimed.
