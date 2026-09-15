"""Nebius Token Factory - OpenAI-compatible inference (chat + embeddings)."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .config import settings


class TokenFactoryError(RuntimeError):
    pass


# Token Factory serves chat, embedding, guardrail and image models from one
# /models list. Embedding IDs don't reliably say "embed" (e.g. BAAI/bge-en-icl),
# so match the families explicitly.
_NON_CHAT_MARKERS = (
    "embed", "bge-", "e5-", "gte-", "guard", "rerank",
    "flux", "stable-diffusion", "sdxl", "whisper",
)

# Preferred families when picking a default, best first.
_PREFERRED = ("instruct", "gpt-oss", "chat", "-it")


def is_chat_model(model_id: str) -> bool:
    """True when a model ID looks like a text/chat model rather than an embedder."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


def _headers() -> Dict[str, str]:
    if not settings.token_factory_ready:
        raise TokenFactoryError("NEBIUS_API_KEY is not set")
    return {
        "Authorization": f"Bearer {settings.nebius_api_key}",
        "Content-Type": "application/json",
    }


async def list_models() -> List[str]:
    """Model IDs available to this Token Factory account."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{settings.nebius_base_url}/models", headers=_headers())
    if response.status_code >= 400:
        raise TokenFactoryError(
            f"Token Factory /models returned {response.status_code}: {response.text[:300]}"
        )
    return sorted(m.get("id", "") for m in response.json().get("data", []) if m.get("id"))


_cached_default: Optional[str] = None


async def default_chat_model() -> str:
    """NEBIUS_MODEL if set, otherwise the first non-embedding model on the account."""
    global _cached_default
    if settings.nebius_model:
        return settings.nebius_model
    if _cached_default:
        return _cached_default

    chat_models = [m for m in await list_models() if is_chat_model(m)]
    if not chat_models:
        raise TokenFactoryError("No chat-capable models found on this account")

    for marker in _PREFERRED:
        for model in chat_models:
            if marker in model.lower():
                _cached_default = model
                return _cached_default

    _cached_default = chat_models[0]
    return _cached_default


async def embed(texts: List[str], model: Optional[str] = None) -> List[List[float]]:
    """Embed a batch of texts. Used to semantically rerank Tavily sources."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.nebius_base_url}/embeddings",
            headers=_headers(),
            json={"model": model or settings.embedding_model, "input": texts},
        )
    if response.status_code >= 400:
        raise TokenFactoryError(
            f"Token Factory /embeddings returned {response.status_code}: {response.text[:300]}"
        )
    data = sorted(response.json()["data"], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in data]


async def stream_chat(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float = 0.3,
    max_tokens: int = 1600,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream a chat completion. Yields {'delta': str} then {'usage': {...}}."""
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST", f"{settings.nebius_base_url}/chat/completions", headers=_headers(), json=body
        ) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:300]
                raise TokenFactoryError(
                    f"Token Factory /chat/completions returned {response.status_code}: {detail}"
                )

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                for choice in parsed.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield {"delta": delta}

                if parsed.get("usage"):
                    yield {"usage": parsed["usage"]}
