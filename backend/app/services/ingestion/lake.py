"""Immutable raw storage.

Two interchangeable backends behind one function:

  * **local filesystem** (default) — zero configuration, so the project runs
    with no infrastructure at all; and
  * **S3-compatible object storage** (MinIO, AWS S3, any S3 API) when an
    endpoint is configured.

Both write the identical partition layout, `source_type/year/month/day/<id>.json`,
because that layout *is* the contract: collect once, never mutate, replay from
raw. Swapping the backend changes where bytes land and nothing else.

Failures in either backend never block ingestion — the durable record is the
`raw_events` table; the lake is a replayable mirror of it.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

_s3_client = None
_s3_retry_after = 0.0

# After a connection failure, stop hammering the object store — but do retry.
# A permanent latch would pin a long-running process to local disk for a
# restart that lasted seconds.
_RETRY_COOLDOWN_SECONDS = 60


def _client():
    """Lazy S3 client. A failure here degrades to local disk rather than
    losing the write, and is retried once the cooldown expires."""
    global _s3_client, _s3_retry_after
    if _s3_client is not None:
        return _s3_client
    if time.monotonic() < _s3_retry_after:
        return None
    try:
        import boto3
        from botocore.config import Config

        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
        )
        try:
            _s3_client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            _s3_client.create_bucket(Bucket=settings.s3_bucket)
            log.info("created lake bucket %s", settings.s3_bucket)
        log.info("raw lake using S3 backend at %s", settings.s3_endpoint_url)
        return _s3_client
    except Exception as exc:
        _s3_client = None
        _s3_retry_after = time.monotonic() + _RETRY_COOLDOWN_SECONDS
        log.warning(
            "S3 lake unavailable (%s); using local disk, retrying in %ds",
            exc,
            _RETRY_COOLDOWN_SECONDS,
        )
        return None


def partition_path(source_type: str, collected_at: datetime) -> Path:
    return (
        Path(settings.raw_lake_dir)
        / source_type.lower()
        / f"{collected_at:%Y}"
        / f"{collected_at:%m}"
        / f"{collected_at:%d}"
    )


def object_key(raw_id: uuid.UUID, source_type: str, collected_at: datetime) -> str:
    """The partition path, identical across both backends."""
    return (
        f"{source_type.lower()}/{collected_at:%Y}/{collected_at:%m}/{collected_at:%d}/{raw_id}.json"
    )


def _document(raw_id: uuid.UUID, source_type: str, collected_at: datetime, payload: dict) -> str:
    return json.dumps(
        {
            "id": str(raw_id),
            "source_type": source_type,
            "collected_at": collected_at.isoformat(),
            "schema_version": 1,
            "payload": payload,
        },
        ensure_ascii=False,
        indent=2,
    )


def write_raw(raw_id: uuid.UUID, source_type: str, collected_at: datetime, payload: dict) -> str | None:
    if settings.s3_enabled:
        client = _client()
        if client is not None:
            key = object_key(raw_id, source_type, collected_at)
            try:
                client.put_object(
                    Bucket=settings.s3_bucket,
                    Key=key,
                    Body=_document(raw_id, source_type, collected_at, payload).encode("utf-8"),
                    ContentType="application/json",
                )
                return f"s3://{settings.s3_bucket}/{key}"
            except Exception as exc:
                global _s3_client, _s3_retry_after
                _s3_client = None
                _s3_retry_after = time.monotonic() + _RETRY_COOLDOWN_SECONDS
                log.warning("S3 lake write failed for %s: %s", raw_id, exc)
                # fall through to local disk
    try:
        directory = partition_path(source_type, collected_at)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{raw_id}.json"
        target.write_text(
            _document(raw_id, source_type, collected_at, payload), encoding="utf-8"
        )
        return str(target)
    except OSError as exc:
        log.warning("raw lake write failed for %s: %s", raw_id, exc)
        return None


def lake_stats() -> dict:
    if settings.s3_enabled:
        client = _client()
        if client is not None:
            try:
                paginator = client.get_paginator("list_objects_v2")
                objects = 0
                prefixes = set()
                for page in paginator.paginate(Bucket=settings.s3_bucket):
                    for obj in page.get("Contents", []):
                        objects += 1
                        prefixes.add(obj["Key"].rsplit("/", 1)[0])
                return {
                    "backend": "s3",
                    "root": f"s3://{settings.s3_bucket}",
                    "endpoint": settings.s3_endpoint_url,
                    "partitions": len(prefixes),
                    "objects": objects,
                }
            except Exception as exc:
                log.warning("S3 lake stats failed: %s", exc)

    root = Path(settings.raw_lake_dir)
    if not root.exists():
        return {"backend": "local", "root": str(root), "partitions": 0, "objects": 0}
    partitions = {p.parent for p in root.rglob("*.json")}
    return {
        "backend": "local",
        "root": str(root),
        "partitions": len(partitions),
        "objects": sum(1 for _ in root.rglob("*.json")),
    }
