from typing import Any, Literal
from pydantic import BaseModel, Field


Level = Literal["L1", "L2", "L3"]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    level: Level | None = None
    question_id: str | None = None


class Citation(BaseModel):
    document: str
    uri: str | None = None
    excerpt: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    trace_id: str
    reasoning: str | None = None


class RetrievedChunk(BaseModel):
    document: str
    text: str
    score: float | None = None       # vector search score from KB retrieve()
    rerank_score: float | None = None  # cross-encoder score from Bedrock Rerank
    uri: str | None = None
    location: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalTrace(BaseModel):
    knowledge_base_id: str
    top_k: int
    chunks: list[RetrievedChunk]


class ToolCallRecord(BaseModel):
    tool_name: str
    params: str        # brief param summary, e.g. "service=PaymentGW"
    result_hint: str   # brief result, e.g. "p99=185ms, error=0.08%"


class ModelTrace(BaseModel):
    model_id: str
    prompt_policy: str
    latency_ms: int | None = None


class TraceRecord(BaseModel):
    trace_id: str
    request_id: str
    session_id: str | None = None
    level: Level
    question_id: str | None = None
    question: str
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    retrieval: RetrievalTrace | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    model: ModelTrace | None = None
    logs: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
