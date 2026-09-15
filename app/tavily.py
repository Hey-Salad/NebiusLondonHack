"""Tavily web search - the sourcing stage of the pipeline."""

from typing import Any, Dict, List

import httpx

from .config import settings


class TavilyError(RuntimeError):
    pass


async def search(
    query: str,
    max_results: int = 8,
    topic: str = "general",
    search_depth: str = "advanced",
    time_range: str = "",
) -> List[Dict[str, Any]]:
    """Run a Tavily search and return normalised source records."""
    if not settings.tavily_ready:
        raise TavilyError("TAVILY_API_KEY is not set")

    payload: Dict[str, Any] = {
        "query": query,
        "max_results": max(1, min(max_results, 20)),
        "topic": topic,
        "search_depth": search_depth,
        "include_answer": False,
        "chunks_per_source": 3,
    }
    if time_range:
        payload["time_range"] = time_range

    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            settings.tavily_url,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json=payload,
        )

    if response.status_code >= 400:
        raise TavilyError(f"Tavily returned {response.status_code}: {response.text[:300]}")

    results = response.json().get("results", [])
    sources = []
    for item in results:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        sources.append(
            {
                "title": (item.get("title") or item.get("url") or "Untitled").strip(),
                "url": item.get("url", ""),
                "content": content,
                "tavily_score": round(float(item.get("score") or 0.0), 4),
                "published_date": item.get("published_date") or "",
            }
        )
    return sources
