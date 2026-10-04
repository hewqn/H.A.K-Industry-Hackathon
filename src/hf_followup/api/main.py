"""Backend API with durable persistence, workflow, overrides, and audit.

/api/v1/docs contracts are available at /docs. Voice uses browser client tools
with scoped local evidence grants. Mutations use the command protocol (PRD §25).
"""

import os
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from hf_followup.api.schemas import (
    CohortRead,
    ComparisonRequest,
    ContextRequest,
    ModelsRead,
    MutationResult,
    OverrideRequest,
    PatientCreateRequest,
    PatientDeleteRequest,
    PatientRead,
    PatientUpdateRequest,
    ResetRequest,
    Snapshot,
    SnapshotRequest,
    Summary,
    SummaryRequest,
    ToolRequest,
    VoiceContextRead,
    VoiceSessionRead,
    VoiceSessionRequest,
    WorkflowRequest,
)
from hf_followup.config import Settings
from hf_followup.data.ingest import ingest_csv
from hf_followup.domain.errors import DomainError
from hf_followup.domain.predictions import ModelRisks
from hf_followup.evaluation.benchmark import case_benchmark
from hf_followup.repositories.predictions import load_prediction_bundle
from hf_followup.services.application import ApplicationService
from hf_followup.services.voice import VoiceService


def _create_repository(settings: Settings):
    """Create the best available repository: Databricks if configured, else SQLite."""
    hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
    catalog = os.getenv("HF_CATALOG", "")

    if hostname and catalog:
        try:
            from hf_followup.repositories.databricks import DatabricksRepository

            repo = DatabricksRepository()
            repo.connect().close()  # Verify the connection works.
            return repo, "databricks"
        except Exception:
            pass  # Fall through to SQLite.

    # SQLite fallback — always available.
    from hf_followup.repositories.sqlite import SQLiteRepository

    db_path = settings.root / "runtime" / "local.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteRepository(db_path), "sqlite"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        # This local bootstrap is the only evaluator boundary. Outcomes are discarded
        # after aggregate evaluation and are never supplied to the service or tools.
        ingestion = ingest_csv(settings.root / "data/heart_failure_clinical_records.csv")
        report = case_benchmark(ingestion.cohort, ingestion.outcomes)
        predictions = load_prediction_bundle(settings.model_bundle_dir, ingestion.cohort)
        repo, repo_mode = _create_repository(settings)
        app.state.repo_mode = repo_mode
        app.state.service = ApplicationService(
            ingestion.cohort, report, settings, predictions, repository=repo
        )
        del ingestion  # Release evaluator labels before the application starts serving requests.
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as voice_client:
            app.state.voice = VoiceService(settings, app.state.service, voice_client)
            yield

    app = FastAPI(title="Heart-failure follow-up scaffold", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        # Patient CRUD needs PUT/DELETE; scoped voice evidence uses Authorization.
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/voice/"):
            response.headers["Cache-Control"] = "no-store"
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

    def voice_service(request: Request) -> VoiceService:
        svc = request.app.state.voice
        svc.require_origin(request.headers.get("origin"))
        return svc

    prefix = "/api/v1"

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get(prefix + "/health")
    def health(request: Request, svc=Depends(service)):
        return {
            "core": "ready",
            "mode": request.app.state.repo_mode,
            "databricks": "connected" if request.app.state.repo_mode == "databricks" else "not_connected",
            "voice": "configured" if request.app.state.voice.configured else "not_configured",
            "persistence": request.app.state.repo_mode,
            "ml": "frozen_cache_ready" if svc.prediction_bundle else "not_published",
            "model_bundle_id": svc.prediction_bundle.manifest["bundle_id"]
            if svc.prediction_bundle
            else None,
        }

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @app.get(prefix + "/cohorts/current", response_model=CohortRead)
    def cohort(svc=Depends(service)):
        return svc.cohort_read()

    @app.get(prefix + "/models", response_model=ModelsRead)
    def models(svc=Depends(service)):
        return svc.models()

    @app.get(prefix + "/ranking-snapshots/{snapshot_id}", response_model=Snapshot)
    def snapshot(snapshot_id: str, svc=Depends(service)):
        return svc.snapshot(snapshot_id)

    # Patient CRUD — POST must be registered before GET {patient_id} so
    # FastAPI doesn't try to match "patients" as a path parameter.
    @app.post(prefix + "/patients")
    def add_patient(body: PatientCreateRequest, svc=Depends(service)):
        facts = {
            "age": body.age,
            "anaemia": body.anaemia,
            "creatinine_phosphokinase": body.creatinine_phosphokinase,
            "diabetes": body.diabetes,
            "ejection_fraction": body.ejection_fraction,
            "high_blood_pressure": body.high_blood_pressure,
            "platelets": body.platelets,
            "serum_creatinine": body.serum_creatinine,
            "serum_sodium": body.serum_sodium,
            "sex": body.sex,
            "smoking": body.smoking,
        }
        return svc.add_patient(body.command_id, body.expected_revision, facts)

    @app.get(prefix + "/patients/{patient_id}", response_model=PatientRead)
    def patient(patient_id: str, snapshot_id: str = Query(max_length=100), svc=Depends(service)):
        return svc.patient(patient_id, snapshot_id)

    @app.get(prefix + "/patients/{patient_id}/risks", response_model=ModelRisks)
    def patient_risks(
        patient_id: str, snapshot_id: str = Query(max_length=100), svc=Depends(service)
    ):
        risks = svc.patient(patient_id, snapshot_id)["model_risks"]
        if risks is None:
            raise DomainError(
                "model_unavailable",
                "Publish the frozen models with make publish-models or make train first.",
                503,
            )
        return risks

    @app.post(prefix + "/patients/{patient_id}/summary", response_model=Summary)
    def summary(patient_id: str, body: SummaryRequest, svc=Depends(service)):
        patient = svc.patient(patient_id, body.snapshot_id)
        if patient["evidence_digest"] != body.evidence_digest:
            raise DomainError("stale_evidence", "Summary digest differs from this snapshot.", 409)
        return patient["summary"]

    @app.post(prefix + "/comparisons/heart-weight")
    def comparison(body: ComparisonRequest, svc=Depends(service)):
        if body.cohort_id != svc.cohort.manifest["cohort_id"]:
            raise DomainError("cohort_not_found", "Use the fixed bundled cohort.", 404)
        return svc.benchmark

    # ------------------------------------------------------------------
    # Mutations (all go through the command protocol)
    # ------------------------------------------------------------------

    @app.post(prefix + "/ranking-snapshots", response_model=MutationResult)
    def create_snapshot(body: SnapshotRequest, svc=Depends(service)):
        if body.cohort_id != svc.cohort.manifest["cohort_id"]:
            raise DomainError("cohort_not_found", "Requested cohort is not active.", 404)
        return svc.create_snapshot_command(
            body.command_id, body.expected_revision,
            body.method_id, body.capacity, body.mode,
        )

    @app.patch(prefix + "/patients/{patient_id}/workflow")
    def workflow(patient_id: str, body: WorkflowRequest, svc=Depends(service)):
        return svc.transition_workflow(
            body.command_id, body.expected_revision,
            patient_id, body.state, body.reason,
        )

    @app.post(prefix + "/overrides")
    def overrides(body: OverrideRequest, svc=Depends(service)):
        return svc.apply_override(
            body.command_id, body.expected_revision,
            body.patient_id, body.action, body.reason, body.session_id,
        )

    @app.put(prefix + "/patients/{patient_id}")
    def update_patient(patient_id: str, body: PatientUpdateRequest, svc=Depends(service)):
        updates = {
            k: v for k, v in {
                "age": body.age,
                "anaemia": body.anaemia,
                "creatinine_phosphokinase": body.creatinine_phosphokinase,
                "diabetes": body.diabetes,
                "ejection_fraction": body.ejection_fraction,
                "high_blood_pressure": body.high_blood_pressure,
                "platelets": body.platelets,
                "serum_creatinine": body.serum_creatinine,
                "serum_sodium": body.serum_sodium,
                "sex": body.sex,
                "smoking": body.smoking,
            }.items() if v is not None
        }
        if not updates:
            raise DomainError("no_updates", "No fields to update.", 422)
        return svc.update_patient(body.command_id, body.expected_revision, patient_id, updates)

    @app.delete(prefix + "/patients/{patient_id}")
    def delete_patient(patient_id: str, body: PatientDeleteRequest, svc=Depends(service)):
        return svc.delete_patient(
            body.command_id, body.expected_revision, patient_id, body.reason,
        )

    @app.post(prefix + "/sessions/reset")
    def reset(body: ResetRequest, svc=Depends(service)):
        return svc.reset_session(
            body.command_id, body.expected_revision, body.reason,
        )

    # ------------------------------------------------------------------
    # Audit and export
    # ------------------------------------------------------------------

    @app.get(prefix + "/audit-events")
    def audit_events(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        svc=Depends(service),
    ):
        return svc.audit_events(limit, offset)

    @app.get(prefix + "/exports/queue.csv")
    def export(snapshot_id: str = Query(max_length=100), svc=Depends(service)):
        csv_content = svc.export_queue_csv(snapshot_id)
        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="queue-{snapshot_id[:8]}.csv"'},
        )

    # ------------------------------------------------------------------
    # Voice: provider credentials stay here; browser tools carry scoped grants.
    # ------------------------------------------------------------------

    @app.post(prefix + "/voice/context", response_model=VoiceContextRead)
    def voice_context(body: ContextRequest, request: Request, svc=Depends(voice_service)):
        # Text evidence has no provider dependency and consumes no voice credits.
        svc.rate_limit(request.client.host if request.client else "local")
        return svc.context(body)

    @app.post(prefix + "/voice/session", response_model=VoiceSessionRead)
    async def voice_session(body: VoiceSessionRequest, request: Request, svc=Depends(voice_service)):
        svc.rate_limit(request.client.host if request.client else "local")
        return await svc.session(body)

    @app.post(prefix + "/voice/tools/{tool_name}")
    def voice_tool(tool_name: str, body: ToolRequest, request: Request, svc=Depends(voice_service)):
        authorization = request.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else None
        return svc.tool(tool_name, body, token)

    return app


app = create_app()
