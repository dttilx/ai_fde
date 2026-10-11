import asyncio
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.access.routes import router as access_router
from app.diagnosis.claim_review_routes import router as claim_review_router
from app.diagnosis.routes import router as diagnosis_router
from app.diagnosis.service import execute_diagnosis
from app.evidence.processing import process_media
from app.evidence.routes import router as evidence_router
from app.expert.routes import router as expert_router
from app.feedback.processing import publish_case_job
from app.feedback.routes import router as feedback_router
from app.incidents.routes import asset_router
from app.incidents.routes import router as incidents_router
from app.knowledge.assessment_routes import router as assessment_router
from app.safety.routes import router as safety_router
from app.safety.service import evaluate
from app.shared.config import settings
from app.shared.errors import DomainError
from app.shared.jobs.executor import ExecutorRegistry
from app.shared.jobs.worker import Worker
from app.shared.logging import log_event


@asynccontextmanager
async def lifespan(app):
    registry = ExecutorRegistry()
    registry.register("DIAGNOSIS", execute_diagnosis)
    registry.register("OCR", process_media)
    registry.register("VIDEO", process_media)
    registry.register("CASE_PUBLICATION", publish_case_job)
    worker = Worker(registry, timeout=120)

    async def serve():
        while True:
            try:
                await asyncio.to_thread(worker.reconcile_expired)
                if not await worker.run_once():
                    await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                raise
            except Exception:
                log_event("worker.failed", trace_id="worker", code="WORKER_OPERATION_FAILED")
                await asyncio.sleep(1)

    task = asyncio.create_task(serve())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="APX-240 Field Diagnosis", version="0.1.0", lifespan=lifespan)
app.include_router(access_router)
app.include_router(incidents_router)
app.include_router(asset_router)
app.include_router(safety_router)
app.include_router(diagnosis_router)
app.include_router(claim_review_router)
app.include_router(assessment_router)
app.include_router(evidence_router)
app.include_router(expert_router)
app.include_router(feedback_router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.trace_id = uuid4().hex
    try:
        response = await call_next(request)
    except Exception:
        log_event("request.failed", trace_id=request.state.trace_id, code="INTERNAL_ERROR")
        response = JSONResponse(
            {"code": "INTERNAL_ERROR", "trace_id": request.state.trace_id}, status_code=500
        )
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError):
    notice = await rejected_input_safety(request)
    return JSONResponse(
        {"code": exc.code, "trace_id": request.state.trace_id, "immediate_safety_notice": notice},
        status_code=exc.status,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    notice = await rejected_input_safety(request)
    return JSONResponse(
        {
            "code": "INVALID_INPUT",
            "trace_id": request.state.trace_id,
            "immediate_safety_notice": notice,
        },
        status_code=422,
    )


async def rejected_input_safety(request: Request):
    if request.url.path != "/api/incidents":
        return None
    try:
        body = await request.json()
    except Exception:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("raw_description"), str):
        return None
    decision = evaluate(body["raw_description"][:5000], {})
    return decision.model_dump() if decision.safety_blocked else None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "apx240", "mode": settings().provider_mode}
