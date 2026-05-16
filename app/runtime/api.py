import logging
import os
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI

load_dotenv()

from app.contracts import A2AMessage, InvocationRequest, InvocationResponse
from app.runtime.auth import require_entra_user
from app.runtime.logging_config import configure_logging
from app.runtime.router import AgentRouter

logger = logging.getLogger(__name__)

configure_logging()

app = FastAPI(title="Catering Multi-Agent Runtime", version="0.2.0")
router = AgentRouter()

if os.getenv("ENABLE_OTEL", "").strip().lower() in ("1", "true", "yes"):
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("OpenTelemetry FastAPI instrumentation enabled")
    except ImportError:
        logger.warning(
            "ENABLE_OTEL is set but opentelemetry packages are missing. "
            "Install: opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi"
        )


@app.get("/health")
def health() -> dict:
    from app.platform.config import platform_metadata

    return {"status": "ok", "platform": platform_metadata()}


@app.post("/invocations", response_model=InvocationResponse)
def invoke(
    req: InvocationRequest,
    _auth: dict = Depends(require_entra_user),
) -> InvocationResponse:
    body = req.model_dump()
    thread_id = (body.pop("thread_id") or "").strip() or str(uuid4())
    correlation_id = thread_id
    logger.info("invocation_started thread_id=%s event_type=%s", thread_id, req.event_type)
    result = router.invoke_catering_flow(body, thread_id)
    logger.info("invocation_completed thread_id=%s", thread_id)
    return InvocationResponse(
        correlation_id=correlation_id,
        thread_id=result["thread_id"],
        message_trace=result["message_trace"],
        final_report=result["final_report"],
    )


@app.post("/a2a/messages")
def a2a_message(
    msg: A2AMessage,
    _auth: dict = Depends(require_entra_user),
) -> dict:
    return router.dispatch_message(msg)
