"""Listing photos with STORAGE_BACKEND=supabase, against an in-memory fake
bucket (httpx.MockTransport) - no network."""
import json

import httpx
import pytest

from app.core.config import get_settings
from app.modules.commerce import images as image_limits, storage
from test_listing_images import _files, _jpeg, _setup

pytestmark = pytest.mark.asyncio
settings = get_settings()

BASE = "https://proj.supabase.co"
PUBLIC = f"{BASE}/storage/v1/object/public/listing-images/"


class FakeBucket:
    """Implements just the two Supabase Storage endpoints this app uses."""

    def __init__(self, fail_on=None):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_on = fail_on  # optional predicate(key) -> True to simulate a 500 on upload

    def __call__(self, request: httpx.Request) -> httpx.Response:
        prefix = "/storage/v1/object/listing-images"
        path = request.url.path
        if request.method == "POST" and path.startswith(prefix + "/"):
            key = path[len(prefix) + 1:]
            if self.fail_on and self.fail_on(key):
                return httpx.Response(500, json={"error": "boom"})
            self.objects[key] = request.content
            return httpx.Response(200, json={"Key": f"listing-images/{key}"})
        if request.method == "DELETE" and path == prefix:
            keys = json.loads(request.content)["prefixes"]
            self.deleted.extend(keys)
            for key in keys:
                self.objects.pop(key, None)
            return httpx.Response(200, json=[])
        return httpx.Response(404)


def _enable_bucket(monkeypatch, bucket: FakeBucket | None = None) -> FakeBucket:
    bucket = bucket or FakeBucket()
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", BASE)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "listing-images")
    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(bucket))
    return bucket


async def test_photos_go_to_the_bucket_and_are_served_from_direct_cdn_urls(client, monkeypatch):
    bucket = _enable_bucket(monkeypatch)
    headers, org_slug, listing = await _setup(client, "Bucket Farm A", "bkt1@example.com")

    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg()))
    assert up.status_code == 201
    photos = up.json()

    assert len(bucket.objects) == 4  # a full-size + a thumbnail object per photo
    assert all(k.count("/") == 2 and listing["id"] in k for k in bucket.objects)  # org/listing/image keying
    for photo in photos:
        assert photo["url"].startswith(PUBLIC) and photo["thumb_url"].startswith(PUBLIC)
        assert photo["url"].removeprefix(PUBLIC) in bucket.objects and photo["thumb_url"].removeprefix(PUBLIC) in bucket.objects

    # the public API hands shoppers the direct CDN links, cover first
    detail = (await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")).json()
    assert [(i["id"], i["url"], i["thumb_url"]) for i in detail["images"]] == [(p["id"], p["url"], p["thumb_url"]) for p in photos]

    # the admin grid gets the cover thumbnail's direct URL
    grid = (await client.get("/api/v1/listings", headers=headers)).json()[0]
    assert grid["cover_thumb_url"] == photos[0]["thumb_url"] and grid["image_count"] == 2


async def test_media_endpoint_redirects_bucket_photos_to_their_cdn_url(client, monkeypatch):
    _enable_bucket(monkeypatch)
    headers, _, listing = await _setup(client, "Bucket Farm B", "bkt2@example.com")
    photo = (await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg()))).json()[0]

    full = await client.get(f"/api/v1/media/listing-images/{photo['id']}", follow_redirects=False)
    thumb = await client.get(f"/api/v1/media/listing-images/{photo['id']}/thumb", follow_redirects=False)
    assert full.status_code == thumb.status_code == 302
    assert full.headers["location"] == photo["url"] and thumb.headers["location"] == photo["thumb_url"]


async def test_deleting_a_photo_removes_both_bucket_objects(client, monkeypatch):
    bucket = _enable_bucket(monkeypatch)
    headers, _, listing = await _setup(client, "Bucket Farm C", "bkt3@example.com")
    first, second = (await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg()))).json()

    assert (await client.delete(f"/api/v1/listings/{listing['id']}/images/{first['id']}", headers=headers)).status_code == 204
    assert sorted(bucket.deleted) == sorted([first["url"].removeprefix(PUBLIC), first["thumb_url"].removeprefix(PUBLIC)])
    assert sorted(bucket.objects) == sorted([second["url"].removeprefix(PUBLIC), second["thumb_url"].removeprefix(PUBLIC)])
    remaining = (await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)).json()
    assert [(i["id"], i["position"]) for i in remaining] == [(second["id"], 0)]


async def test_a_failed_upload_leaves_no_rows_and_no_orphaned_objects(client, monkeypatch):
    # the FIRST photo's full-size object uploads fine, then a thumbnail upload fails
    bucket = _enable_bucket(monkeypatch, FakeBucket(fail_on=lambda key: key.endswith("_thumb.jpg")))
    headers, _, listing = await _setup(client, "Bucket Farm D", "bkt4@example.com")

    resp = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg()))
    assert resp.status_code == 502
    assert bucket.objects == {}  # the already-uploaded full-size object was cleaned up
    assert (await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)).json() == []


async def test_bucket_backend_that_is_not_configured_fails_clearly_with_503(client, monkeypatch):
    _enable_bucket(monkeypatch)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")  # half-configured
    headers, _, listing = await _setup(client, "Bucket Farm E", "bkt5@example.com")
    resp = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg()))
    assert resp.status_code == 503 and "not configured" in resp.json()["detail"]
    assert (await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)).json() == []


async def test_going_over_the_photo_cap_cleans_up_the_objects_it_just_uploaded(client, monkeypatch):
    bucket = _enable_bucket(monkeypatch)
    headers, _, listing = await _setup(client, "Bucket Farm F", "bkt6@example.com")
    cap = image_limits.MAX_IMAGES_PER_LISTING
    ok = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(*[_jpeg(64, 64)] * cap))
    assert ok.status_code == 201 and len(bucket.objects) == cap * 2

    over = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(64, 64)))
    assert over.status_code == 409
    assert len(bucket.objects) == cap * 2  # the extra photo's objects were removed again


async def test_database_and_bucket_photos_coexist_after_switching_backends(client, monkeypatch):
    headers, org_slug, listing = await _setup(client, "Bucket Farm G", "bkt7@example.com")
    # uploaded while still on the default database backend
    db_photo = (await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg()))).json()[0]
    assert db_photo["url"] is None

    bucket = _enable_bucket(monkeypatch)
    bucket_photo = (await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg()))).json()[0]
    assert bucket_photo["position"] == 1 and bucket_photo["url"].startswith(PUBLIC)

    # old photo is still served by the API (bytes, no redirect); new one redirects to the CDN
    old = await client.get(f"/api/v1/media/listing-images/{db_photo['id']}", follow_redirects=False)
    assert old.status_code == 200 and old.headers["content-type"] == "image/jpeg"
    new = await client.get(f"/api/v1/media/listing-images/{bucket_photo['id']}", follow_redirects=False)
    assert new.status_code == 302

    detail = (await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")).json()
    assert [(i["id"], i["url"] is None) for i in detail["images"]] == [(db_photo["id"], True), (bucket_photo["id"], False)]
    assert len(bucket.objects) == 2  # only the new photo is in the bucket
