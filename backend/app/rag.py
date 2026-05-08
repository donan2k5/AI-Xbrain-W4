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
    ToolCallRecord,
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
- When search_knowledge_base returns results, each chunk is labeled [1], [2], etc. Use those same numbers as inline citations in your answer.
- For real-time/database tool results, no inline citation needed — just reference the data directly.
- When a document makes a general statement AND lists specific items, prioritize the specific items in your answer over the general statement.
- For ANY question about a specific incident or outage (root cause, timeline, what happened, why, resolution, action items): use ONLY search_knowledge_base. Never query the database for incident-specific questions.
- When two sources conflict, resolve by priority: (1) newer version or date wins, (2) document explicitly marked as superseding another wins, (3) more specific document wins over a general one. Always cite both sources and state which one you trust and why in one phrase — e.g. "v2 supersedes v1 [1][2]" or "the March 2026 policy overrides the earlier version [1][3]".

Start immediately with the fact — never open with "The search returned", "I found", "Based on", or any meta-commentary. 1-2 sentences of prose. No bullets, no numbered lists, no headers. For sequences use "→". Cite ALL sources that contributed — list every relevant [n] at the end of the sentence.

Good examples:
- "The rate limit is 1,000 requests per minute per merchant API key [1][2]."
- "Yes — the freeze (Fri 18:00–Mon 08:00) can be overridden for P1 hotfixes with VP Engineering Mark Sullivan approval [1][3]."
- "PaymentGW and OrderSvc are the explicitly documented direct dependencies of AuthSvc [2][4]; a full AuthSvc outage would affect the entire platform since all services rely on it for token validation [1]."
- "AuthSvc is written in Go [1]."

Output only the answer — no section headers, no preamble."""


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
        "description": "Fetch real-time metrics for a specific service (p50/p95/p99 latency, error rate, requests/min, CPU/memory). Use for current live data. For ALL services at once pass service_name='all'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service name: PaymentGW, NotificationSvc, AuthSvc, OrderSvc, FraudDetector, InventorySvc, ReportingSvc — or 'all' for all services",
                }
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "query_database",
        "description": (
            "Run a read-only SQL SELECT on the GeekBrain SQLite database. "
            "Exact schema:\n"
            "  monthly_costs(id, service, month, compute_cost, storage_cost, network_cost, third_party_cost, total_cost)\n"
            "  incidents(incident_id, service, date, severity, duration_minutes, root_cause_summary, resolution, team_responsible, reported_by)\n"
            "  sla_targets(id, service, metric, target, measurement_window)\n"
            "  daily_metrics(id, date, service, latency_p99_ms, error_rate_percent, requests_per_minute, availability_percent)\n"
            "Use ONLY for: monthly costs, SLA targets, and daily metric trends. "
            "Do NOT use for any question about a specific incident or outage — use search_knowledge_base for all incident questions including basic details, root cause, timeline, or resolution. "
            "The incidents table exists only for aggregate stats (e.g. COUNT of incidents per service); never query it to answer 'what happened' or 'why'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT SQL statement to execute",
                }
            },
            "required": ["sql"],
        },
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


def _make_tool_executor(adapter: BedrockAdapter, settings: Settings, citation_map: dict, chunk_list: list, tool_calls_log: list):
    citation_counter = [0]

    def execute_tool(tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_knowledge_base":
            query = tool_input.get("query", "")
            chunks, _ = adapter.retrieve(query, settings.retrieval_top_k)
            if not chunks:
                tool_calls_log.append(ToolCallRecord(tool_name=tool_name, params=f'"{query[:60]}"', result_hint="No documents found"))
                return "No relevant documents found."
            chunks = adapter.rerank(query, chunks, settings.rerank_top_n)
            parts = []
            for chunk in chunks:
                citation_counter[0] += 1
                idx = citation_counter[0]
                citation_map[idx] = chunk
                chunk_list.append(chunk)
                parts.append(f"[{idx}] {chunk.document}\n{_strip_frontmatter(chunk.text).replace(chr(10), ' ')}")
            tool_calls_log.append(ToolCallRecord(
                tool_name=tool_name,
                params=f'"{query[:60]}"',
                result_hint=f"{len(chunks)} chunks: {', '.join(dict.fromkeys(c.document for c in chunks))[:80]}",
            ))
            return "\n\n".join(parts)

        if tool_name == "fetch_service_metrics":
            service = tool_input.get("service_name", "")
            try:
                if service.lower() == "all":
                    result = tools_module.fetch_all_services_metrics()
                    hint = f"all services fetched"
                else:
                    result = tools_module.fetch_service_metrics(service)
                    d = result if isinstance(result, dict) else {}
                    hint = f"p99={d.get('latency_p99_ms','?')}ms, error={d.get('error_rate_percent','?')}%, rpm={d.get('requests_per_minute','?')}"
                formatted = tools_module.format_for_llm(result)
                tool_calls_log.append(ToolCallRecord(tool_name=tool_name, params=f"service={service}", result_hint=hint))
                return formatted
            except Exception as e:
                tool_calls_log.append(ToolCallRecord(tool_name=tool_name, params=f"service={service}", result_hint=f"ERROR: {e}"))
                return json.dumps({"error": str(e)})

        if tool_name == "query_database":
            sql = tool_input.get("sql", "").strip()
            if not sql.upper().startswith("SELECT"):
                return json.dumps({"error": "Only SELECT queries allowed"})
            try:
                result = tools_module.query_database(sql)
                formatted = tools_module.format_for_llm(result)
                rows = result if isinstance(result, list) else []
                hint = f"{len(rows)} rows" + (f": {json.dumps(rows[0])[:60]}" if rows else "")
                tool_calls_log.append(ToolCallRecord(tool_name=tool_name, params=sql[:80], result_hint=hint))
                return formatted
            except Exception as e:
                tool_calls_log.append(ToolCallRecord(tool_name=tool_name, params=sql[:80], result_hint=f"ERROR: {e}"))
                return json.dumps({"error": str(e)})

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    return execute_tool


_META_PREAMBLE = re.compile(
    r'^(the search|i found|i can see|based on|looking at|from the|according to the search)',
    re.I
)


def _clean_answer(raw: str) -> str:
    """Strip any meta-commentary preamble lines that don't contain citations."""
    lines = raw.strip().splitlines()
    while lines and _META_PREAMBLE.match(lines[0].strip()) and not re.search(r'\[\d+\]', lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip() or raw.strip()


def _citations_from_map(answer: str, citation_map: dict) -> tuple[str, list[Citation]]:
    """Extract inline [n] markers, deduplicate by document, remap to sequential indices.

    Returns (remapped_answer, citations) so displayed [1][2][3] always match sources list.
    """
    # Preserve first-appearance order of cited indices
    cited_indices = list(dict.fromkeys(int(m) for m in re.findall(r'\[(\d+)\]', answer)))

    doc_to_new: dict[str, int] = {}
    old_to_new: dict[int, int] = {}
    citations: list[Citation] = []

    for old_idx in cited_indices:
        chunk = citation_map.get(old_idx)
        if not chunk:
            continue
        if chunk.document not in doc_to_new:
            new_idx = len(doc_to_new) + 1
            doc_to_new[chunk.document] = new_idx
            citations.append(Citation(
                document=chunk.document,
                uri=chunk.uri,
                excerpt=chunk.text.strip().replace("\n", " ")[:240],
            ))
        old_to_new[old_idx] = doc_to_new[chunk.document]

    def _remap(m: re.Match) -> str:
        new = old_to_new.get(int(m.group(1)))
        return f"[{new}]" if new else ""

    remapped_answer = re.sub(r'\[(\d+)\]', _remap, answer)
    return remapped_answer, citations


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
        tool_calls_log: list = []
        tool_executor = _make_tool_executor(adapter, settings, citation_map, chunk_list, tool_calls_log)

        logs.append(log_event("agent_started", tools_available=len(TOOL_DEFINITIONS)))
        raw_answer, thinking, latency_ms = adapter.converse_with_tools(
            AGENT_SYSTEM_PROMPT,
            request.message,
            tools=TOOL_DEFINITIONS,
            tool_executor=tool_executor,
        )
        logs.append(log_event("agent_finished", latency_ms=latency_ms))
        logger.info("agent finished trace_id=%s level=%s latency_ms=%s", trace_id, level, latency_ms)

        answer = _clean_answer(raw_answer)

        answer, citations = _citations_from_map(answer, citation_map)
        if chunk_list and not citations:
            citations = _fallback_citations(chunk_list)

        record.answer = answer
        record.citations = citations
        record.tool_calls = tool_calls_log
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
