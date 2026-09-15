"""Salad Scout - HeySalad food intelligence, powered by Tavily + Nebius."""

import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, tokenfactory
from .config import settings

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Salad Scout", description="HeySalad food intelligence on Nebius")
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    max_results: int = Field(default=8, ge=3, le=20)
    keep: int = Field(default=6, ge=2, le=12)
    topic: str = "general"
    time_range: str = ""
    model: str = ""


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {
        "tavily": settings.tavily_ready,
        "token_factory": settings.token_factory_ready,
        "object_storage": settings.storage_ready,
        "model": settings.nebius_model or "auto",
        "embedding_model": settings.embedding_model,
        "missing": settings.missing(),
    }


@app.get("/api/models")
async def models() -> Dict[str, Any]:
    if not settings.token_factory_ready:
        return {"models": [], "chat_models": [], "error": "NEBIUS_API_KEY is not set"}
    try:
        available = await tokenfactory.list_models()
        return {
            "models": available,
            "chat_models": [m for m in available if tokenfactory.is_chat_model(m)],
        }
    except Exception as exc:
        return {"models": [], "chat_models": [], "error": str(exc)[:300]}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/research")
async def research(request: ResearchRequest) -> StreamingResponse:
    if missing := settings.missing():
        return JSONResponse({"error": f"Missing config: {missing}"}, status_code=400)

    async def events() -> AsyncIterator[str]:
        try:
            async for item in pipeline.run(
                query=request.query,
                max_results=request.max_results,
                keep=request.keep,
                topic=request.topic,
                model=request.model,
                time_range=request.time_range,
            ):
                yield _sse(item["event"], item["data"])
        except Exception as exc:
            yield _sse("error", {"message": f"{exc.__class__.__name__}: {exc}"[:400]})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
