import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.bedrock_adapter import BedrockAdapter
from app.config import Settings, get_settings
from app.models import ChatRequest, ChatResponse, TraceRecord
from app.rag import run_rag_chat
from app.traces import trace_store

app = FastAPI(title="AI-XBrain RAG API", version="0.1.0")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ai_xbrain")

settings_for_cors = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_for_cors.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def log_startup() -> None:
    settings = get_settings()
    logger.info(
        "hello backend: started region=%s kb_configured=%s model=%s proxy_disabled=%s",
        settings.aws_region,
        bool(settings.bedrock_kb_id),
        settings.bedrock_model_id,
        settings.aws_disable_proxy,
    )


def get_adapter(settings: Settings = Depends(get_settings)) -> BedrockAdapter:
    return BedrockAdapter(settings)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
    adapter: BedrockAdapter = Depends(get_adapter),
) -> ChatResponse:
    try:
        logger.info("chat request received level=%s question_id=%s", request.level, request.question_id)
        return run_rag_chat(request, settings, adapter)
    except Exception as exc:
        logger.exception("chat request failed")
        raise HTTPException(status_code=502, detail=f"RAG request failed: {exc}") from exc


@app.get("/api/traces/{trace_id}", response_model=TraceRecord)
def get_trace(trace_id: str) -> TraceRecord:
    trace = trace_store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
