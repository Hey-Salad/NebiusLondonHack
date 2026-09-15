"""Environment-backed settings for Salad Scout."""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _clean(name: str, default: str = "") -> str:
    value = (os.getenv(name) or default).strip()
    # Treat leftover placeholders ("your-key-here", "tvly-xxxx...") as unset, so
    # the UI says "add your key" instead of the API returning a bare 401.
    if "xxxx" in value.lower() or value.lower().startswith("your-"):
        return ""
    return value


@dataclass
class Settings:
    # Tavily
    tavily_api_key: str = field(default_factory=lambda: _clean("TAVILY_API_KEY"))
    tavily_url: str = field(
        default_factory=lambda: _clean("TAVILY_URL", "https://api.tavily.com/search")
    )

    # Nebius Token Factory
    nebius_api_key: str = field(default_factory=lambda: _clean("NEBIUS_API_KEY"))
    nebius_base_url: str = field(
        default_factory=lambda: _clean(
            "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"
        ).rstrip("/")
    )
    nebius_model: str = field(default_factory=lambda: _clean("NEBIUS_MODEL"))
    embedding_model: str = field(
        default_factory=lambda: _clean("NEBIUS_EMBEDDING_MODEL", "BAAI/bge-en-icl")
    )

    # Nebius AI Cloud Object Storage (optional)
    bucket: str = field(default_factory=lambda: _clean("NEBIUS_STORAGE_BUCKET"))
    storage_region: str = field(
        default_factory=lambda: _clean("NEBIUS_STORAGE_REGION", "eu-north1")
    )
    storage_endpoint: str = field(
        default_factory=lambda: _clean(
            "NEBIUS_STORAGE_ENDPOINT", "https://storage.eu-north1.nebius.cloud"
        )
    )
    storage_key_id: str = field(
        default_factory=lambda: _clean("NEBIUS_STORAGE_ACCESS_KEY_ID")
    )
    storage_secret: str = field(
        default_factory=lambda: _clean("NEBIUS_STORAGE_SECRET_ACCESS_KEY")
    )

    port: int = field(default_factory=lambda: int(_clean("PORT", "8000")))

    @property
    def tavily_ready(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def token_factory_ready(self) -> bool:
        return bool(self.nebius_api_key)

    @property
    def storage_ready(self) -> bool:
        return bool(self.bucket and self.storage_key_id and self.storage_secret)

    def missing(self) -> Optional[str]:
        """Human-readable description of what still needs configuring."""
        gaps = []
        if not self.tavily_ready:
            gaps.append("TAVILY_API_KEY")
        if not self.token_factory_ready:
            gaps.append("NEBIUS_API_KEY")
        return ", ".join(gaps) or None


settings = Settings()
