"""Bounded downloads from one operator-configured private Supabase namespace."""

import asyncio
from collections.abc import Callable
from pathlib import Path
import re
from urllib.parse import quote

import httpx

from app.config import Settings
from app.errors import ServiceError

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".m4v"}


def validate_object_path(object_path: str, prefix: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,1023}", object_path)
        or any(part in ("", ".", "..") for part in object_path.split("/"))
        or not object_path.startswith(prefix + "/")
        or Path(object_path).suffix.lower() not in VIDEO_SUFFIXES
    ):
        raise ServiceError(
            422, "invalid_storage_path", "Use a video object inside the configured storage prefix."
        )
    return object_path


async def download_private_video(
    object_path: str,
    destination: Path,
    settings: Settings,
    *,
    client_factory: Callable = httpx.AsyncClient,
) -> None:
    validate_object_path(object_path, settings.storage_prefix)
    if not settings.supabase_url or settings.supabase_service_key is None:
        raise ServiceError(
            503, "storage_not_configured", "Private storage is not configured on this server."
        )
    url = (
        settings.supabase_url.rstrip("/")
        + "/storage/v1/object/authenticated/"
        + quote(settings.storage_bucket, safe="")
        + "/"
        + quote(object_path, safe="/")
    )
    key = settings.supabase_service_key.get_secret_value()
    try:
        async with asyncio.timeout(settings.upload_timeout_seconds):
            async with client_factory(
                timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "apikey": key,
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code == 404:
                        raise ServiceError(
                            404, "video_not_found", "The storage object was not found."
                        )
                    if response.status_code != 200:
                        raise ServiceError(
                            502,
                            "storage_download_failed",
                            "Private storage could not provide the video.",
                        )
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise ServiceError(
                            502,
                            "encoded_storage_response",
                            "Storage must provide an uncompressed video response.",
                        )
                    declared = response.headers.get("Content-Length")
                    if declared is not None and (
                        not declared.isdigit() or int(declared) > settings.max_video_bytes
                    ):
                        raise ServiceError(
                            413, "video_too_large", "The storage video exceeds the byte limit."
                        )
                    size = 0
                    with destination.open("xb") as handle:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            size += len(chunk)
                            if size > settings.max_video_bytes:
                                raise ServiceError(
                                    413,
                                    "video_too_large",
                                    "The storage video exceeds the byte limit.",
                                )
                            handle.write(chunk)
                    if size == 0:
                        raise ServiceError(422, "empty_video", "The storage video is empty.")
    except ServiceError:
        raise
    except (httpx.HTTPError, TimeoutError):
        raise ServiceError(502, "storage_unavailable", "Private storage is unavailable.") from None
