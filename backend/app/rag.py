import json
import logging
import re
import uuid

from app.bedrock_adapter import BedrockAdapter
from app.config import Settings
from app.models import (
    ChatRequest,
    ChatResponse,
    Citation,
    ModelTrace,
    RetrievalTrace,
    TraceRecord,
)
from app.traces import log_event, trace_store
from app import tools as tools_module

logger = logging.getLogger("ai_xbrain.rag")


AGENT_SYSTEM_PROMPT = """You are an intelligent assistant for the GeekBrain platform. You have access to two types of information:

1. **search_knowledge_base** — Use for questions about policies, API specs, team ownership, deployment rules, incident processes, SLA definitions, security guidelines, rate limits, or any documented facts.

2. **Real-time & historical data tools** — Use for current service metrics (latency, error rate, CPU), costs, incidents log, SLA compliance, and operational data.

For every question:
- Decide what information you need and call the right tool(s). You may call multiple tools.
- When search_knowledge_base returns results, each chunk is labeled [1], [2], etc. Use those same numbers as inline citations in your ANSWER.
- For real-time/database tool results, no inline citation needed — just reference the data directly.
- When a document makes a general statement AND lists specific items, prioritize the specific items in your answer over the general statement.

Always respond in this exact format:

THINKING:
[Your reasoning: what the question is asking, which tools you chose and why, what the results tell you]

ANSWER:
[Start immediately with the fact — never open with "The search returned", "I found", "Based on", or any meta-commentary. 1-2 sentences of prose. No bullets, no numbered lists, no headers. For sequences use "→".
Cite ALL sources that contributed — list every relevant [n] at the end of the sentence.

Good examples:
- "The rate limit is 1,000 requests per minute per merchant API key [1][2]."
- "Yes — the freeze (Fri 18:00–Mon 08:00) can be overridden for P1 hotfixes with VP Engineering Mark Sullivan approval [1][3]."
- "PaymentGW and OrderSvc are the explicitly documented direct dependencies of AuthSvc [2][4]; a full AuthSvc outage would affect the entire platform since all services rely on it for token validation [1]."
- "AuthSvc is written in Go [1]."]"""


TOOL_DEFINITIONS = [
    {
        "name": "search_knowledge_base",
        "description": "Search documentation for policies, API specs, team ownership, deployment rules, incident processes, security guidelines, rate limits, SLA definitions, postmortem reports (root cause analysis, incident timelines, action items), runbooks, architecture reviews, and other documented facts. Use this for any question about WHY something happened, how a process works, or what a policy says.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query describing the information needed",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_service_metrics",
        "description": "Fetch real-time metrics for a specific service: p50/p95/p99 latency, error rate, requests/min, CPU/memory utilization.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service name: PaymentGW, NotificationSvc, AuthSvc, OrderSvc, FraudDetector, InventorySvc, ReportingSvc",
                }
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "fetch_all_services_metrics",
        "description": "Fetch real-time metrics for all services at once.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_service_costs",
        "description": "Get monthly costs for a specific service, optionally filtered by month (YYYY-MM).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name"},
                "month": {"type": "string", "description": "Month in YYYY-MM format, e.g. 2026-03"},
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "get_all_costs",
        "description": "Get monthly costs for all services, optionally filtered by month.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "Month in YYYY-MM format"},
            },
            "required": [],
        },
    },
    {
        "name": "get_service_incidents",
        "description": "Get brief incident records for a service (ID, date, severity, short description). Use for counting incidents or listing dates. Does NOT contain root cause analysis or postmortem detail — use search_knowledge_base for that.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name"},
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "get_sla_targets",
        "description": "Get SLA targets for one or all services.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name (omit for all services)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_daily_metrics",
        "description": "Get historical daily metrics for a service within a date range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Service name"},
                "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "get_service_comparison",
        "description": "Compare a metric across all services using the latest daily metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metric_name": {
                    "type": "string",
                    "description": "One of: latency_p99_ms, latency_p95_ms, latency_p50_ms, error_rate_percent, requests_per_minute, availability_percent",
                }
            },
            "required": ["metric_name"],
        },
    },
    {
        "name": "get_q1_costs_summary",
        "description": "Get Q1 2026 (January–March) total and average costs aggregated by service.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _strip_frontmatter(text: str) -> str:
    """Remove YAML --- frontmatter so model and trace see actual content."""
    stripped = text.strip()
    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end != -1:
            return stripped[end + 4:].lstrip("\n")
    return stripped


def _make_tool_executor(adapter: BedrockAdapter, settings: Settings, citation_map: dict, chunk_list: list):
    """Return a tool executor closure that tracks KB citation mapping."""
    citation_counter = [0]

    def execute_tool(tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_knowledge_base":
            query = tool_input.get("query", "")
            chunks, _ = adapter.retrieve(query, settings.retrieval_top_k)
            if not chunks:
                return "No relevant documents found."
            chunks = adapter.rerank(query, chunks, settings.rerank_top_n)
            parts = []
            for chunk in chunks:
                citation_counter[0] += 1
                idx = citation_counter[0]
                citation_map[idx] = chunk
                chunk_list.append(chunk)
                excerpt = _strip_frontmatter(chunk.text).replace("\n", " ")
                parts.append(f"[{idx}] {chunk.document}\n{excerpt}")
            return "\n\n".join(parts)

        try:
            if tool_name == "fetch_service_metrics":
                result = tools_module.fetch_service_metrics(tool_input.get("service_name", ""))
            elif tool_name == "fetch_all_services_metrics":
                result = tools_module.fetch_all_services_metrics()
            elif tool_name == "get_service_costs":
                result = tools_module.get_service_costs(
                    tool_input.get("service_name", ""),
                    tool_input.get("month"),
                )
            elif tool_name == "get_all_costs":
                result = tools_module.get_all_costs(tool_input.get("month"))
            elif tool_name == "get_service_incidents":
                result = tools_module.get_service_incidents(tool_input.get("service_name", ""))
            elif tool_name == "get_sla_targets":
                result = tools_module.get_sla_targets(tool_input.get("service_name"))
            elif tool_name == "get_daily_metrics":
                result = tools_module.get_daily_metrics(
                    tool_input.get("service_name", ""),
                    tool_input.get("date_from"),
                    tool_input.get("date_to"),
                )
            elif tool_name == "get_service_comparison":
                result = tools_module.get_service_comparison(tool_input.get("metric_name", "latency_p99_ms"))
            elif tool_name == "get_q1_costs_summary":
                result = tools_module.get_q1_costs_summary()
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            return tools_module.format_for_llm(result)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})

    return execute_tool


_THINKING_PREAMBLE = re.compile(
    r'^(the search|i found|i can see|based on|looking at|from the|according to the search)',
    re.I
)


def _parse_agent_response(raw: str) -> tuple[str, str]:
    """Parse THINKING and ANSWER blocks from agent response."""
    thinking_lines: list[str] = []
    answer_lines: list[str] = []
    section = "thinking"  # default to thinking so preamble before THINKING: goes there too

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("THINKING:"):
            section = "thinking"
            rest = stripped[len("THINKING:"):].strip()
            if rest:
                thinking_lines.append(rest)
        elif stripped.upper().startswith("ANSWER:"):
            section = "answer"
            rest = stripped[len("ANSWER:"):].strip()
            if rest:
                answer_lines.append(rest)
        elif section == "thinking" and stripped:
            thinking_lines.append(stripped)
        elif section == "answer" and stripped:
            answer_lines.append(stripped)

    thinking = "\n".join(thinking_lines).strip()
    answer = "\n".join(answer_lines).strip()

    # Strip leading reasoning sentences that leaked into the answer block:
    # if the first line looks like meta-commentary and has no citation, move it to thinking.
    if answer:
        lines = answer.splitlines()
        while lines and _THINKING_PREAMBLE.match(lines[0]) and not re.search(r'\[\d+\]', lines[0]):
            thinking_lines.append(lines.pop(0))
        answer = "\n".join(lines).strip()
        thinking = "\n".join(thinking_lines).strip()

    if not answer:
        answer = raw.strip()
    return thinking, answer


def _citations_from_map(answer: str, citation_map: dict) -> list[Citation]:
    """Extract inline [n] markers from answer and build Citation list."""
    indices = {int(m) for m in re.findall(r'\[(\d+)\]', answer)}
    seen: set[str] = set()
    citations: list[Citation] = []
    for idx in sorted(indices):
        chunk = citation_map.get(idx)
        if chunk and chunk.document not in seen:
            seen.add(chunk.document)
            citations.append(Citation(
                document=chunk.document,
                uri=chunk.uri,
                excerpt=chunk.text.strip().replace("\n", " ")[:240],
            ))
    return citations


def _fallback_citations(chunk_list: list) -> list[Citation]:
    """When no inline markers found but KB was searched, return top unique docs."""
    seen: set[str] = set()
    citations: list[Citation] = []
    for chunk in chunk_list:
        if chunk.document not in seen:
            seen.add(chunk.document)
            citations.append(Citation(
                document=chunk.document,
                uri=chunk.uri,
                excerpt=chunk.text.strip().replace("\n", " ")[:240],
            ))
        if len(citations) >= 3:
            break
    return citations


def run_rag_chat(request: ChatRequest, settings: Settings, adapter: BedrockAdapter) -> ChatResponse:
    if not settings.bedrock_kb_id:
        raise ValueError("BEDROCK_KB_ID is not configured. Copy backend/.env.example to backend/.env and set it.")

    trace_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    # Level is kept for tracing/logging only — no routing
    level = request.level or (
        request.question_id.upper()[:2] if request.question_id and len(request.question_id) >= 2 else "L3"
    )

    logs = [log_event("request_received", level=level, question_id=request.question_id)]
    record = TraceRecord(
        trace_id=trace_id,
        request_id=request_id,
        session_id=request.session_id,
        level=level,
        question_id=request.question_id,
        question=request.message,
        logs=logs,
    )

    try:
        citation_map: dict[int, object] = {}
        chunk_list: list = []
        tool_executor = _make_tool_executor(adapter, settings, citation_map, chunk_list)

        logs.append(log_event("agent_started", tools_available=len(TOOL_DEFINITIONS)))
        raw_answer, latency_ms = adapter.converse_with_tools(
            AGENT_SYSTEM_PROMPT,
            request.message,
            tools=TOOL_DEFINITIONS,
            tool_executor=tool_executor,
        )
        logs.append(log_event("agent_finished", latency_ms=latency_ms))
        logger.info("agent finished trace_id=%s level=%s latency_ms=%s", trace_id, level, latency_ms)

        thinking, answer = _parse_agent_response(raw_answer)

        citations = _citations_from_map(answer, citation_map)
        if chunk_list and not citations:
            citations = _fallback_citations(chunk_list)

        record.answer = answer
        record.citations = citations
        if chunk_list:
            record.retrieval = RetrievalTrace(
                knowledge_base_id=settings.bedrock_kb_id,
                top_k=len(chunk_list),
                chunks=chunk_list,
            )
        record.model = ModelTrace(
            model_id=settings.bedrock_model_id,
            prompt_policy="unified agent",
            latency_ms=latency_ms,
        )
        trace_store.put(record)
        return ChatResponse(answer=answer, citations=citations, trace_id=trace_id, reasoning=thinking or None)

    except Exception as exc:
        logs.append(log_event("request_failed", error=str(exc)))
        record.error = str(exc)
        trace_store.put(record)
        logger.exception("agent request failed trace_id=%s", trace_id)
        raise
