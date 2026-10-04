# Scaffold architecture

```mermaid
flowchart LR
  CSV[Bundled CSV] --> Ingest[Validate and assign source IDs]
  Ingest --> Features[Allowlisted patient features]
  Ingest --> Outcomes[Evaluator-only outcomes]
  Features --> Rank[Shared Python ranking]
  Features --> Train[Frozen development-only training]
  Outcomes --> Train
  Train --> Artifacts[Trusted versioned pipelines and metadata]
  Artifacts --> Inference[Batch inference]
  Features --> Inference
  Inference --> Cache[Checksummed three-risk JSON cache]
  Cache --> Rank
  Cache --> API
  Outcomes --> Benchmark[Historical evaluator]
  Benchmark --> Reports[Aggregate descriptive reports]
  Rank --> API[FastAPI read-only starter]
  Reports --> API
  API --> React[React selected patient and snapshot]
  React --> Viewer[3D engineer interface and text cards]
  Databricks[Databricks Delta and MLflow — TODO] -.-> API
  Voice[ElevenLabs — TODO] -.-> API
```

Solid arrows are the local starter. Dashed arrows require owner implementation and
real integration verification. This diagram describes boundaries, not deployed services.

`domain/` owns deterministic calculations; no database/provider/training side effects.
`data/` separates outcomes from features at ingest. `evaluation/` may access outcomes
and publishes aggregates. `ml/` supplies frozen training, inference and publication.
The API loads only JSON through `repositories/predictions.py`; model loading stays offline.
`services/` owns the one patient evidence envelope. `api/` adapts it to HTTP/Pydantic.
`repositories/` is the backend owner's data/persistence interface. React owns selected
patient/snapshot and rejects stale responses. The engineer's anatomy module consumes
interpreted indicators and emits organ-selection events, without CSV or scoring logic.

Databricks is the intended primary data/ML and durable event backend. Local SQLite is
an optional cache/outbox to implement, not an existing primary store. A vector database,
multi-agent framework, task queue, and production healthcare deployment are not required.

Default frontend development proxy: browser `/api/v1` → FastAPI `127.0.0.1:8000`.
No provider key enters browser code. Real voice webhooks need protected HTTPS reachable
by ElevenLabs; browser client tools are the alternative for a local API.
