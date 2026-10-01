"""Supabase storage client - exercised against a mock transport (no network,
no database). Confirms the requests we send match Supabase's documented
Storage REST API shape and that failures surface cleanly."""
import json
import uuid

import httpx
import pytest

from app.modules.commerce import storage

CFG = storage.StorageConfig(
    backend="supabase", supabase_url="https://abc.supabase.co", service_key="service-key-123", bucket="listing-images",
)


@pytest.fixture
def calls(monkeypatch):
    """Installs a recording mock transport; returns the list of captured requests."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "ok"})

    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(handler))
    return seen


def test_object_keys_are_tenant_prefixed_and_distinct():
    org, listing, image = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    full, thumb = storage.object_keys(org, listing, image)
    assert full == f"{org}/{listing}/{image}.jpg" and thumb == f"{org}/{listing}/{image}_thumb.jpg"


def test_public_url_uses_the_public_object_path():
    assert storage.public_url(CFG, "o/l/i.jpg") == "https://abc.supabase.co/storage/v1/object/public/listing-images/o/l/i.jpg"


def test_config_reads_settings_and_strips_trailing_slash():
    class S:
        STORAGE_BACKEND = " Supabase "
        SUPABASE_URL = "https://abc.supabase.co/"
        SUPABASE_SERVICE_ROLE_KEY = "k"
        SUPABASE_STORAGE_BUCKET = "b"

    cfg = storage.config_from_settings(S())
    assert cfg.use_bucket and cfg.configured and cfg.supabase_url == "https://abc.supabase.co" and cfg.backend == "supabase"


def test_database_backend_is_default_and_never_uses_the_bucket():
    class S:
        STORAGE_BACKEND = ""
        SUPABASE_URL = ""
        SUPABASE_SERVICE_ROLE_KEY = ""
        SUPABASE_STORAGE_BUCKET = "listing-images"

    cfg = storage.config_from_settings(S())
    assert cfg.backend == "database" and not cfg.use_bucket
    assert storage.config_warning(cfg) is None


def test_startup_warnings_for_half_configured_or_unknown_backend():
    half = storage.StorageConfig("supabase", "", "", "b")
    assert "will fail with 503" in storage.config_warning(half)
    assert "falling back" in storage.config_warning(storage.StorageConfig("s3", "", "", "b"))
    assert storage.config_warning(CFG) is None


@pytest.mark.asyncio
async def test_upload_sends_the_documented_request(calls):
    await storage.upload_object(CFG, "o/l/i.jpg", b"JPEGBYTES", "image/jpeg")
    (req,) = calls
    assert req.method == "POST"
    assert str(req.url) == "https://abc.supabase.co/storage/v1/object/listing-images/o/l/i.jpg"
    assert req.headers["authorization"] == "Bearer service-key-123" and req.headers["apikey"] == "service-key-123"
    assert req.headers["content-type"] == "image/jpeg"
    assert req.headers["x-upsert"] == "false"       # never silently overwrite an existing object
    assert "max-age" in req.headers["cache-control"]
    assert req.content == b"JPEGBYTES"


@pytest.mark.asyncio
async def test_new_style_secret_key_is_sent_on_the_apikey_header_only(monkeypatch):
    seen = []
    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200))[1]))
    cfg = storage.StorageConfig("supabase", "https://abc.supabase.co", "sb_secret_abc123", "listing-images")
    await storage.upload_object(cfg, "k.jpg", b"x", "image/jpeg")
    await storage.delete_objects(cfg, ["k.jpg"])
    for req in seen:
        assert req.headers["apikey"] == "sb_secret_abc123"
        assert "authorization" not in req.headers  # not a JWT - must not be sent as a Bearer token


@pytest.mark.asyncio
async def test_legacy_jwt_service_role_key_is_sent_on_both_headers(calls):
    legacy = storage.StorageConfig("supabase", "https://abc.supabase.co", "eyJhbGciOi.payload.sig", "listing-images")
    await storage.upload_object(legacy, "k.jpg", b"x", "image/jpeg")
    (req,) = calls
    assert req.headers["authorization"] == "Bearer eyJhbGciOi.payload.sig" and req.headers["apikey"] == "eyJhbGciOi.payload.sig"


def test_secret_key_setting_takes_precedence_over_the_legacy_name():
    class S:
        STORAGE_BACKEND = "supabase"
        SUPABASE_URL = "https://abc.supabase.co"
        SUPABASE_SECRET_KEY = "sb_secret_new"
        SUPABASE_SERVICE_ROLE_KEY = "legacy-jwt"
        SUPABASE_STORAGE_BUCKET = "b"

    assert storage.config_from_settings(S()).service_key == "sb_secret_new"
    S.SUPABASE_SECRET_KEY = ""
    assert storage.config_from_settings(S()).service_key == "legacy-jwt"  # falls back for existing setups


@pytest.mark.asyncio
async def test_upload_failure_raises_without_leaking_credentials(monkeypatch):
    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(lambda r: httpx.Response(403, json={"error": "denied"})))
    with pytest.raises(storage.StorageError) as exc:
        await storage.upload_object(CFG, "k.jpg", b"x", "image/jpeg")
    assert "403" in str(exc.value) and "service-key-123" not in str(exc.value)


@pytest.mark.asyncio
async def test_network_failure_becomes_a_storage_error(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(boom))
    with pytest.raises(storage.StorageError):
        await storage.upload_object(CFG, "k.jpg", b"x", "image/jpeg")


@pytest.mark.asyncio
async def test_upload_refuses_when_not_configured(calls):
    with pytest.raises(storage.StorageNotConfigured):
        await storage.upload_object(storage.StorageConfig("supabase", "", "", "b"), "k.jpg", b"x", "image/jpeg")
    assert calls == []  # nothing was sent anywhere


@pytest.mark.asyncio
async def test_delete_sends_bulk_prefixes_body(calls):
    await storage.delete_objects(CFG, ["a.jpg", "a_thumb.jpg"])
    (req,) = calls
    assert req.method == "DELETE" and str(req.url) == "https://abc.supabase.co/storage/v1/object/listing-images"
    assert json.loads(req.content) == {"prefixes": ["a.jpg", "a_thumb.jpg"]}
    assert req.headers["authorization"] == "Bearer service-key-123"


@pytest.mark.asyncio
async def test_delete_is_best_effort_and_never_raises(monkeypatch):
    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(lambda r: httpx.Response(500)))
    await storage.delete_objects(CFG, ["a.jpg"])          # HTTP error: swallowed (logged)

    def boom(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(boom))
    await storage.delete_objects(CFG, ["a.jpg"])          # network error: swallowed (logged)


@pytest.mark.asyncio
async def test_delete_with_nothing_to_do_makes_no_request(calls):
    await storage.delete_objects(CFG, [])
    await storage.delete_objects(storage.StorageConfig("supabase", "", "", "b"), ["a.jpg"])
    assert calls == []
