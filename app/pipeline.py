"""The Salad Scout pipeline: Tavily -> Token Factory -> Nebius AI Cloud."""

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List

from . import storage, tavily, tokenfactory
from .config import settings

SYSTEM_PROMPT = """You are Salad Scout, HeySalad's food-intelligence analyst.
You brief busy food founders, chefs and buyers.

Rules:
- Answer ONLY from the numbered sources provided. Never invent facts or figures.
- Cite every claim inline like [1] or [2][4]. Cite the source you actually used.
- If the sources disagree or don't cover something, say so plainly.
- Be warm, direct and useful. Short sentences. No corporate jargon.

Structure your answer in markdown:
## The short answer
Two or three sentences a reader could act on today.

## What the sources say
Three to five bullets, each with citations.

## What this means for HeySalad
Two or three bullets of practical implication.

## Watch-outs
Gaps, stale data or disagreement between sources."""


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def _rerank(query: str, sources: List[Dict[str, Any]], keep: int) -> Dict[str, Any]:
    """Semantically rerank Tavily hits with Token Factory embeddings."""
    snippets = [f"{s['title']}\n{s['content'][:1200]}" for s in sources]
    vectors = await tokenfactory.embed([query] + snippets)
    query_vec, source_vecs = vectors[0], vectors[1:]

    for source, vec in zip(sources, source_vecs):
        source["relevance"] = round(_cosine(query_vec, vec), 4)

    ranked = sorted(sources, key=lambda s: s["relevance"], reverse=True)[:keep]
    used = tokenfactory.last_embedding_model or settings.embedding_model or "auto"
    return {"sources": ranked, "model": used}


def _build_prompt(query: str, sources: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    blocks = []
    for index, source in enumerate(sources, start=1):
        date = f" (published {source['published_date']})" if source["published_date"] else ""
        blocks.append(
            f"[{index}] {source['title']}{date}\nURL: {source['url']}\n{source['content'][:2400]}"
        )
    context = "\n\n".join(blocks)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Question: {query}\n\nSources:\n\n{context}\n\nWrite the briefing now.",
        },
    ]


async def run(
    query: str,
    max_results: int = 8,
    keep: int = 6,
    topic: str = "general",
    model: str = "",
    time_range: str = "",
) -> AsyncIterator[Dict[str, Any]]:
    """Yield SSE-shaped events for one research run."""
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    # 1 - Tavily -----------------------------------------------------------
    yield {"event": "stage", "data": {"id": "search", "status": "running"}}
    sources = await tavily.search(query, max_results=max_results, topic=topic, time_range=time_range)
    if not sources:
        yield {"event": "error", "data": {"message": "Tavily found no usable sources for that query."}}
        return
    yield {
        "event": "stage",
        "data": {"id": "search", "status": "done", "detail": f"{len(sources)} sources", "ms": elapsed()},
    }

    # 2 - Token Factory embeddings ----------------------------------------
    yield {"event": "stage", "data": {"id": "rank", "status": "running"}}
    try:
        ranked = await _rerank(query, sources, keep)
        sources = ranked["sources"]
        rank_detail = f"top {len(sources)} via {ranked['model']}"
        rank_status = "done"
    except Exception as exc:  # embeddings are an enhancement, not a hard dependency
        sources = sources[:keep]
        rank_detail = f"skipped ({exc.__class__.__name__}) - using Tavily order"
        rank_status = "warn"
    yield {"event": "stage", "data": {"id": "rank", "status": rank_status, "detail": rank_detail, "ms": elapsed()}}
    yield {"event": "sources", "data": {"sources": sources}}

    # 3 - Token Factory chat ----------------------------------------------
    chat_model = model or await tokenfactory.default_chat_model()
    yield {"event": "stage", "data": {"id": "brief", "status": "running", "detail": chat_model}}

    answer_parts: List[str] = []
    usage: Dict[str, Any] = {}
    async for chunk in tokenfactory.stream_chat(_build_prompt(query, sources), model=chat_model):
        if "delta" in chunk:
            answer_parts.append(chunk["delta"])
            yield {"event": "delta", "data": {"text": chunk["delta"]}}
        elif "usage" in chunk:
            usage = chunk["usage"]

    answer = "".join(answer_parts)
    yield {
        "event": "stage",
        "data": {
            "id": "brief",
            "status": "done",
            "detail": f"{chat_model} - {usage.get('total_tokens', '?')} tokens",
            "ms": elapsed(),
        },
    }

    # 4 - Nebius AI Cloud Object Storage ----------------------------------
    briefing = {
        "query": query,
        "answer": answer,
        "sources": sources,
        "model": chat_model,
        "embedding_model": settings.embedding_model,
        "usage": usage,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    archived = None
    if settings.storage_ready:
        yield {"event": "stage", "data": {"id": "archive", "status": "running"}}
        try:
            archived = await asyncio.to_thread(storage.archive, briefing)
            yield {
                "event": "stage",
                "data": {"id": "archive", "status": "done", "detail": archived["key"], "ms": elapsed()},
            }
        except Exception as exc:
            yield {
                "event": "stage",
                "data": {"id": "archive", "status": "warn", "detail": str(exc)[:160], "ms": elapsed()},
            }
    else:
        yield {
            "event": "stage",
            "data": {"id": "archive", "status": "skipped", "detail": "Object Storage not configured"},
        }

    yield {"event": "done", "data": {"usage": usage, "model": chat_model, "archived": archived, "ms": elapsed()}}
