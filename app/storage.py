"""Nebius AI Cloud Object Storage - archives each briefing (S3-compatible)."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import settings


class StorageError(RuntimeError):
    pass


def _client():
    try:
        import boto3  # imported lazily so the app runs without boto3 installed
    except ImportError as exc:  # pragma: no cover - depends on install
        raise StorageError("boto3 is not installed (pip install boto3)") from exc

    return boto3.client(
        "s3",
        region_name=settings.storage_region,
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_key_id,
        aws_secret_access_key=settings.storage_secret,
    )


def _slug(text: str, limit: int = 48) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(keep).strip("-").replace("--", "-")[:limit] or "briefing"


def archive(briefing: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Store a briefing as JSON. Returns None when storage isn't configured."""
    if not settings.storage_ready:
        return None

    stamp = datetime.now(timezone.utc)
    key = (
        f"briefings/{stamp:%Y/%m/%d}/"
        f"{stamp:%H%M%S}-{_slug(briefing.get('query', ''))}.json"
    )

    client = _client()
    client.put_object(
        Bucket=settings.bucket,
        Key=key,
        Body=json.dumps(briefing, indent=2, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.bucket, "Key": key},
        ExpiresIn=60 * 60 * 24 * 7,
    )
    return {"bucket": settings.bucket, "key": key, "url": url}
