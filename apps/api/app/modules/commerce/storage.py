"""Object storage for listing photos (Supabase Storage).

Opt-in, same "inert unless configured" pattern as core/vercel_client.py:
`STORAGE_BACKEND=database` (the default) keeps photo bytes in Postgres;
`STORAGE_BACKEND=supabase` uploads them to a Supabase Storage bucket instead
and the browser loads them straight from Supabase's CDN - they never pass
through this API or bloat the database/backups.

Bucket requirements (Supabase dashboard -> Storage): create the bucket named
by SUPABASE_STORAGE_BUCKET and mark it **Public** (listing photos are public by
design; public buckets get CDN-cached direct URLs). The service-role key is
server-side only - it must never reach the frontend.

Same caveat as every external integration in this codebase: written against
Supabase's documented Storage REST API and unit-tested against a mock transport,
NOT exercised against a live project (no network in the build sandbox). Do one
real upload/delete against your project before relying on it.

No FastAPI/pydantic imports here, so it stays trivially unit-testable.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx

logger = logging.getLogger("app.storage")

BACKENDS = ("database", "supabase")
CACHE_CONTROL = "max-age=31536000"  # object keys embed a fresh UUID, so content never changes


class StorageError(Exception):
    """The storage service rejected or couldn't complete an operation."""


class StorageNotConfigured(StorageError):
    """STORAGE_BACKEND=supabase but the URL/key/bucket aren't all set."""


@dataclass(frozen=True)
class StorageConfig:
    backend: str  # "database" | "supabase"
    supabase_url: str
    service_key: str
    bucket: str

    @property
    def use_bucket(self) -> bool:
        return self.backend == "supabase"

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.service_key and self.bucket)


def config_from_settings(settings=None) -> StorageConfig:
    if settings is None:
        from app.core.config import get_settings  # lazy: keeps this module importable without the app config
        settings = get_settings()
    return StorageConfig(
        backend=(settings.STORAGE_BACKEND or "database").strip().lower(),
        supabase_url=(settings.SUPABASE_URL or "").strip().rstrip("/"),
        # SUPABASE_SECRET_KEY is the current name (sb_secret_...); the older
        # SUPABASE_SERVICE_ROLE_KEY name keeps working for existing setups.
        service_key=(getattr(settings, "SUPABASE_SECRET_KEY", "") or settings.SUPABASE_SERVICE_ROLE_KEY or "").strip(),
        bucket=(settings.SUPABASE_STORAGE_BUCKET or "").strip(),
    )


def config_warning(cfg: StorageConfig) -> str | None:
    """A loud-but-non-fatal startup message for a half-configured backend."""
    if cfg.backend not in BACKENDS:
        return f"STORAGE_BACKEND={cfg.backend!r} is not one of {BACKENDS}; falling back to 'database'."
    if cfg.use_bucket and not cfg.configured:
        return (
            "STORAGE_BACKEND=supabase but SUPABASE_URL / SUPABASE_SECRET_KEY / "
            "SUPABASE_STORAGE_BUCKET are not all set - listing photo uploads will fail with 503."
        )
    return None


def object_keys(org_id: uuid.UUID, listing_id: uuid.UUID, image_id: uuid.UUID) -> tuple[str, str]:
    """(full-size key, thumbnail key). Tenant-prefixed so one org's objects are
    always grouped (and listable/purgeable) apart from another's."""
    base = f"{org_id}/{listing_id}/{image_id}"
    return f"{base}.jpg", f"{base}_thumb.jpg"


def public_url(cfg: StorageConfig, key: str) -> str:
    return f"{cfg.supabase_url}/storage/v1/object/public/{cfg.bucket}/{key}"


# Tests inject an httpx.MockTransport here; production leaves it None (real network).
_transport: httpx.AsyncBaseTransport | None = None


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0), transport=_transport)


def _auth_headers(cfg: StorageConfig) -> dict[str, str]:
    """New-style secret keys (`sb_secret_...`) are NOT JWTs: Supabase says to send
    them on the `apikey` header ONLY - putting one in `Authorization: Bearer` can
    be rejected as an invalid JWT. Legacy `service_role` keys are JWTs and are
    sent both ways, as before."""
    headers = {"apikey": cfg.service_key}
    if not cfg.service_key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {cfg.service_key}"
    return headers


async def upload_object(cfg: StorageConfig, key: str, data: bytes, content_type: str) -> None:
    """POST /storage/v1/object/{bucket}/{key}. Never overwrites (x-upsert: false)."""
    if not cfg.configured:
        raise StorageNotConfigured("Photo storage is not configured")
    url = f"{cfg.supabase_url}/storage/v1/object/{cfg.bucket}/{key}"
    headers = {
        **_auth_headers(cfg), "Content-Type": content_type, "x-upsert": "false", "cache-control": CACHE_CONTROL,
    }
    try:
        async with _client() as client:
            response = await client.post(url, content=data, headers=headers)
    except httpx.HTTPError as exc:
        raise StorageError("Could not reach photo storage") from exc
    if response.status_code >= 300:
        # status only - never log headers/body (they could echo credentials)
        logger.warning("storage upload of %s failed with HTTP %s", key, response.status_code)
        raise StorageError(f"Photo storage rejected the upload (HTTP {response.status_code})")


async def delete_objects(cfg: StorageConfig, keys: list[str]) -> None:
    """DELETE /storage/v1/object/{bucket} with {"prefixes": [...]}.
    Best-effort by design: it runs *after* the database change (or as cleanup
    after a failed one), and an orphaned object is harmless, whereas raising
    here would turn a successful delete into an error. Failures are logged."""
    if not keys or not cfg.configured:
        return
    url = f"{cfg.supabase_url}/storage/v1/object/{cfg.bucket}"
    try:
        async with _client() as client:
            response = await client.request("DELETE", url, json={"prefixes": list(keys)}, headers=_auth_headers(cfg))
        if response.status_code >= 300:
            logger.warning("storage delete of %d object(s) failed with HTTP %s", len(keys), response.status_code)
    except Exception:
        logger.exception("storage delete of %d object(s) failed", len(keys))
