"""Backend owner's HTTP entry point with a small, read-only local data slice.

/api/v1/docs contracts are available at /docs. Database/voice/workflow operations
are explicit 503 TODOs, never fake success. Use one writer when implementing PRD §25.
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hf_followup.api.schemas import (
    CohortRead,
    ComparisonRequest,
    ContextRequest,
    MutationResult,
    OverrideRequest,
    PatientRead,
    ResetRequest,
    Snapshot,
    SnapshotRequest,
    Summary,
    SummaryRequest,
    ToolRequest,
    WorkflowRequest,
)
from hf_followup.config import Settings
from hf_followup.data.ingest import ingest_csv
from hf_followup.domain.errors import DomainError
from hf_followup.evaluation.benchmark import case_benchmark
from hf_followup.services.application import ApplicationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        # This local bootstrap is the only evaluator boundary. Outcomes are discarded
        # after aggregate evaluation and are never supplied to the service or tools.
        ingestion = ingest_csv(settings.root / "data/heart_failure_clinical_records.csv")
        report = case_benchmark(ingestion.cohort, ingestion.outcomes)
        app.state.service = ApplicationService(ingestion.cohort, report, settings)
        del ingestion  # Release evaluator labels before the application starts serving requests.
        yield

    app = FastAPI(title="Heart-failure follow-up scaffold", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(DomainError)
    async def error(request: Request, exception: DomainError):
        return JSONResponse(
            status_code=exception.status,
            content={
                "code": exception.code,
                "message": exception.message,
                "request_id": request.state.request_id,
                "retryable": exception.retryable,
            },
        )

    def service(request: Request) -> ApplicationService:
        return request.app.state.service

    def unfinished(requirement: str):
        raise DomainError(
            "integration_pending",
            f"{requirement} integration is intentionally left for its owner. See docs/development.md.",
            503,
        )

    prefix = "/api/v1"

    @app.get(prefix + "/health")
    def health():
        return {
            "core": "scaffold_ready",
            "mode": "in_memory_scaffold",
            "databricks": "not_connected",
            "voice": "not_connected",
            "persistence": "not_implemented",
        }

    @app.get(prefix + "/cohorts/current", response_model=CohortRead)
    def cohort(svc=Depends(service)):
        return svc.cohort_read()

    @app.get(prefix + "/models")
    def models(svc=Depends(service)):
        return svc.models()

    @app.post(prefix + "/ranking-snapshots", response_model=MutationResult)
    def create_snapshot(body: SnapshotRequest, svc=Depends(service)):
        if body.cohort_id != svc.cohort.manifest["cohort_id"]:
            raise DomainError("cohort_not_found", "Requested cohort is not active.", 404)
        # Local previews only. TODO(OPS-01): command IDs/revisions + durable event commit.
        return {
            "snapshot": svc.create_snapshot(body.method_id, body.capacity, body.mode),
            "revision": 0,
            "sync_status": "in_memory_preview",
            "replayed": False,
        }

    @app.get(prefix + "/ranking-snapshots/{snapshot_id}", response_model=Snapshot)
    def snapshot(snapshot_id: str, svc=Depends(service)):
        return svc.snapshot(snapshot_id)

    @app.get(prefix + "/patients/{patient_id}", response_model=PatientRead)
    def patient(patient_id: str, snapshot_id: str = Query(max_length=100), svc=Depends(service)):
        return svc.patient(patient_id, snapshot_id)

    @app.post(prefix + "/patients/{patient_id}/summary", response_model=Summary)
    def summary(patient_id: str, body: SummaryRequest, svc=Depends(service)):
        patient = svc.patient(patient_id, body.snapshot_id)
        if patient["evidence_digest"] != body.evidence_digest:
            raise DomainError("stale_evidence", "Summary digest differs from this snapshot.", 409)
        return patient["summary"]  # Template only; provider/cache implementation remains SUM-01.

    @app.post(prefix + "/comparisons/heart-weight")
    def comparison(body: ComparisonRequest, svc=Depends(service)):
        if body.cohort_id != svc.cohort.manifest["cohort_id"]:
            raise DomainError("cohort_not_found", "Use the fixed bundled cohort.", 404)
        return svc.benchmark  # Descriptive results, not supervised validation or queue mutation.

    @app.patch(prefix + "/patients/{patient_id}/workflow")
    def workflow(patient_id: str, body: WorkflowRequest):
        # TODO(BACKEND, QUEUE-02): transition validation + contact/backfill + reopen reasons.
        return unfinished("Workflow persistence and transitions (QUEUE-02)")

    @app.post(prefix + "/overrides")
    def overrides(body: OverrideRequest):
        # TODO(BACKEND): reasons, pin/defer exclusivity, overflow, snapshot + event atomicity.
        return unfinished("Clinician overrides (QUEUE-02)")

    @app.post(prefix + "/sessions/reset")
    def reset(body: ResetRequest):
        # TODO(BACKEND): retain an audit event; never delete source/model artifacts.
        return unfinished("Audited demo reset (OPS-01)")

    @app.get(prefix + "/audit-events")
    def audit_events():
        # TODO(BACKEND): ordered, paginated immutable events; no secrets in response.
        return unfinished("Audit repository (OPS-01)")

    @app.get(prefix + "/exports/queue.csv")
    def export(snapshot_id: str):
        # TODO(BACKEND): exact snapshot, provenance, summary, CSV escaping/formula neutralization.
        return unfinished("Snapshot handoff export (OPS-01)")

    @app.post(prefix + "/voice/session")
    def voice_session(body: ContextRequest):
        # TODO(API owner): validate active context; request private short-lived signed session.
        # API keys remain server-side. Add allowed origins, timeouts, rate/duration limits.
        return unfinished("ElevenLabs private session (VOICE-01)")

    @app.post(prefix + "/voice/tools/{tool_name}")
    def voice_tool(tool_name: str, body: ToolRequest):
        # TODO(API owner): authenticate and allowlist tools; never accept SQL/URLs/code.
        # Choose protected HTTPS webhooks OR browser client tools in docs/api-integrations.md.
        return unfinished("Authenticated evidence tools (VOICE-01)")

    return app


app = create_app()
