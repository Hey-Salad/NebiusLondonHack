"""Offline end-to-end check: stubs Tavily + Token Factory, drives the real SSE route."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import pipeline, storage, tavily, tokenfactory  # noqa: E402
from app.config import settings  # noqa: E402

settings.tavily_api_key = "tvly-test"
settings.nebius_api_key = "nebius-test"

FAKE_SOURCES = [
    {"title": "Harissa sales up 30% in UK", "url": "https://example.com/a", "content": "Harissa grew 30% year on year.", "tavily_score": 0.9, "published_date": "2026-08-01"},
    {"title": "Spice trends 2026", "url": "https://example.com/b", "content": "Chilli pastes lead the category.", "tavily_score": 0.7, "published_date": ""},
    {"title": "Unrelated page", "url": "https://example.com/c", "content": "Cricket scores from Tuesday.", "tavily_score": 0.4, "published_date": ""},
]


async def fake_search(query, max_results=8, topic="general", search_depth="advanced", time_range=""):
    return list(FAKE_SOURCES)


async def fake_embed(texts, model=None):
    # Crude stand-in: vector = [length, count of "harissa"] so ranking is deterministic.
    return [[float(len(t)), float(t.lower().count("harissa")) * 50] for t in texts]


async def fake_stream(messages, model, temperature=0.3, max_tokens=1600):
    assert "Harissa grew 30%" in messages[1]["content"], "sources must reach the prompt"
    for piece in ["## The short answer\n", "Harissa is growing fast [1].\n\n", "## What the sources say\n", "- Up 30% year on year [1][2]\n"]:
        yield {"delta": piece}
    yield {"usage": {"total_tokens": 412}}


async def main():
    tavily.search = fake_search
    tokenfactory.embed = fake_embed
    tokenfactory.stream_chat = fake_stream
    pipeline.tavily.search = fake_search
    pipeline.tokenfactory.embed = fake_embed
    pipeline.tokenfactory.stream_chat = fake_stream

    events = []
    async for item in pipeline.run("harissa demand uk", max_results=8, keep=2, model="test/model"):
        events.append(item)

    def last_stage(items, stage_id):
        """Stages emit 'running' then a terminal status - take the terminal one."""
        return [e["data"] for e in items if e["event"] == "stage" and e["data"]["id"] == stage_id][-1]

    kinds = [e["event"] for e in events]
    stages = {e["data"]["id"]: e["data"] for e in events if e["event"] == "stage"}
    answer = "".join(e["data"]["text"] for e in events if e["event"] == "delta")
    sources_evt = next(e for e in events if e["event"] == "sources")["data"]["sources"]
    done = next(e for e in events if e["event"] == "done")["data"]

    assert kinds[0] == "stage" and kinds[-1] == "done", kinds
    assert stages["search"]["status"] == "done" and "3 sources" in stages["search"]["detail"]
    assert stages["rank"]["status"] == "done", stages["rank"]
    assert stages["brief"]["status"] == "done" and "412" in stages["brief"]["detail"]
    assert stages["archive"]["status"] == "skipped", stages["archive"]
    assert len(sources_evt) == 2, "keep=2 should trim to two sources"
    assert sources_evt[0]["title"].startswith("Harissa"), "rerank should float harissa to the top"
    assert all("relevance" in s for s in sources_evt)
    assert "[1]" in answer and done["usage"]["total_tokens"] == 412

    # Embedding failure must degrade gracefully rather than kill the run.
    async def boom(texts, model=None):
        raise RuntimeError("embeddings down")

    pipeline.tokenfactory.embed = boom
    degraded = [e async for e in pipeline.run("harissa", keep=2, model="test/model")]
    rank = last_stage(degraded, "rank")
    assert rank["status"] == "warn" and "Tavily order" in rank["detail"], rank
    assert any(e["event"] == "done" for e in degraded), "run must still finish"

    # Object Storage archive path, with boto3 stubbed out.
    settings.bucket, settings.storage_key_id, settings.storage_secret = "scout", "k", "s"
    storage.archive = lambda b: {"bucket": "scout", "key": "briefings/2026/09/15/x.json", "url": "https://signed"}
    pipeline.storage.archive = storage.archive
    pipeline.tokenfactory.embed = fake_embed
    archived = [e async for e in pipeline.run("harissa", keep=2, model="test/model")]
    arch = last_stage(archived, "archive")
    assert arch["status"] == "done" and arch["detail"].endswith(".json"), arch

    print("pipeline events:", json.dumps(kinds[:6]))
    print("PASS - all pipeline assertions")


asyncio.run(main())
