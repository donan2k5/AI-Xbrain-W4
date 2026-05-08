import logging
import time
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger("ai_xbrain.bedrock")

import boto3
from botocore.config import Config

from app.config import Settings
from app.models import RetrievedChunk


def _location_uri(location: dict[str, Any] | None) -> str | None:
    if not location:
        return None
    if "s3Location" in location:
        return location["s3Location"].get("uri")
    if "webLocation" in location:
        return location["webLocation"].get("url")
    return None


def _document_name(uri: str | None, metadata: dict[str, Any]) -> str:
    for key in ("source", "document", "file", "filename", "x-amz-bedrock-kb-source-uri"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return PurePosixPath(value.replace("\\", "/")).name
    if uri:
        return PurePosixPath(uri.replace("\\", "/")).name
    return "unknown-source"


def _wrap_tool_specs(tools: list[dict]) -> list[dict]:
    """Wrap plain tool dicts into Bedrock's toolSpec format."""
    result = []
    for t in tools:
        if "toolSpec" in t:
            result.append(t)
        else:
            result.append({
                "toolSpec": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "inputSchema": {"json": t.get("inputSchema", {})},
                }
            })
    return result


class BedrockAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        client_kwargs = settings.aws_client_kwargs
        if settings.aws_disable_proxy:
            client_kwargs = {**client_kwargs, "config": Config(proxies={})}
        self.agent_runtime = boto3.client("bedrock-agent-runtime", **client_kwargs)
        self.runtime = boto3.client("bedrock-runtime", **client_kwargs)

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        """Rerank chunks using Bedrock Rerank API. Falls back to original order on error."""
        if not chunks:
            return chunks
        try:
            model_arn = f"arn:aws:bedrock:{self.settings.aws_region}::foundation-model/cohere.rerank-v3-5:0"
            response = self.agent_runtime.rerank(
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {
                        "modelConfiguration": {"modelArn": model_arn},
                        "numberOfResults": min(top_n, len(chunks)),
                    },
                },
                sources=[
                    {
                        "type": "INLINE",
                        "inlineDocumentSource": {
                            "type": "TEXT",
                            "textDocument": {"text": chunk.text},
                        },
                    }
                    for chunk in chunks
                ],
                queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            )
            reranked = []
            results = response.get("rerankingResults", [])
            if results:
                logger.debug("rerank result sample keys: %s", list(results[0].keys()))
            for item in results:
                idx = item.get("index")
                if idx is not None and 0 <= idx < len(chunks):
                    rerank_score = item.get("relevanceScore") or item.get("score") or item.get("relevance_score")
                    chunk = chunks[idx].model_copy(update={"rerank_score": rerank_score})
                    reranked.append(chunk)
            return reranked if reranked else chunks[:top_n]
        except Exception as e:
            logger.warning("rerank failed, using original order: %s", e)
            return chunks[:top_n]

    def retrieve(self, question: str, top_k: int) -> tuple[list[RetrievedChunk], int]:
        start = time.perf_counter()
        response = self.agent_runtime.retrieve(
            knowledgeBaseId=self.settings.bedrock_kb_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "overrideSearchType": "HYBRID",
                }
            },
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        chunks: list[RetrievedChunk] = []
        for result in response.get("retrievalResults", []):
            metadata = result.get("metadata") or {}
            location = result.get("location") or {}
            uri = _location_uri(location)
            text = (result.get("content") or {}).get("text", "")
            chunks.append(
                RetrievedChunk(
                    document=_document_name(uri, metadata),
                    text=text,
                    score=result.get("score"),
                    uri=uri,
                    location=location,
                    metadata=metadata,
                )
            )
        return chunks, latency_ms

    def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        start = time.perf_counter()
        response = self.runtime.converse(
            modelId=self.settings.bedrock_model_id,
            system=[{"text": system_prompt}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_prompt}],
                }
            ],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 1200,
            },
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        content = response["output"]["message"].get("content", [])
        answer_parts = [part.get("text", "") for part in content if part.get("text")]
        return "\n".join(answer_parts).strip(), latency_ms

    @staticmethod
    def _extract_thinking(content: list) -> str:
        """Extract thinking text from content blocks. Handles both Bedrock reasoningContent and Anthropic thinking formats."""
        parts = []
        for part in content:
            # Bedrock Converse format
            if rc := part.get("reasoningContent"):
                if rt := rc.get("reasoningText"):
                    parts.append(rt.get("text", ""))
            # Anthropic-style format via additionalModelRequestFields
            elif th := part.get("thinking"):
                if isinstance(th, dict):
                    parts.append(th.get("thinking", ""))
                elif isinstance(th, str):
                    parts.append(th)
        return "\n\n".join(p for p in parts if p)

    def converse_with_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict[str, Any]] | None = None, tool_executor: Any = None
    ) -> tuple[str, str, int]:
        """Converse with tool use + extended thinking. Returns (answer, thinking, latency_ms)."""
        start = time.perf_counter()
        messages = [{"role": "user", "content": [{"text": user_prompt}]}]
        all_thinking: list[str] = []

        converse_args = {
            "modelId": self.settings.bedrock_model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": {
                "temperature": 1,
                "maxTokens": 6000,
            },
            "additionalModelRequestFields": {
                "thinking": {"type": "enabled", "budget_tokens": 2000}
            },
        }

        if tools:
            converse_args["toolConfig"] = {"tools": _wrap_tool_specs(tools)}

        while True:
            response = self.runtime.converse(**converse_args)
            latency_ms = int((time.perf_counter() - start) * 1000)

            content = response["output"]["message"].get("content", [])

            # Collect thinking from this turn
            turn_thinking = self._extract_thinking(content)
            if turn_thinking:
                all_thinking.append(turn_thinking)

            # Check for tool use — must check BEFORE returning text, because
            # Claude can emit thinking AND toolUse in the same turn.
            tool_uses = [part for part in content if part.get("toolUse")]
            if not tool_uses or not tool_executor:
                answer_parts = [part.get("text", "") for part in content if part.get("text")]
                thinking_text = "\n\n".join(all_thinking)
                return "\n".join(answer_parts).strip(), thinking_text, latency_ms

            # Must pass full content back (including thinking blocks) — Bedrock requirement
            messages.append({"role": "assistant", "content": content})

            # Execute tools and collect results
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use["toolUse"]["name"]
                tool_input = tool_use["toolUse"]["input"]
                try:
                    result = tool_executor(tool_name, tool_input)
                    tool_results.append({"toolResult": {
                        "toolUseId": tool_use["toolUse"]["toolUseId"],
                        "content": [{"text": str(result)}],
                        "status": "success",
                    }})
                except Exception as e:
                    tool_results.append({"toolResult": {
                        "toolUseId": tool_use["toolUse"]["toolUseId"],
                        "content": [{"text": f"Error: {str(e)}"}],
                        "status": "error",
                    }})

            # Add tool results to conversation
            messages.append({"role": "user", "content": tool_results})

            # Continue conversation
            converse_args["messages"] = messages
