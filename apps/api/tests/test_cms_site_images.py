"""Logo / banner images uploaded from the device, and banner deletion: upload, public serving, use in the profile
and banners, orphan cleanup, validation, permissions and tenant isolation."""
import io

import pytest
from PIL import Image

pytestmark = pytest.mark.asyncio


def _png(width=400, height=200, color=(30, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


async def _setup(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner", "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    slug = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]
    return headers, slug


async def _upload(client, headers, kind="banner", blob=None, name="pic.png", ctype="image/png"):
    return await client.post(
        f"/api/v1/cms/images?kind={kind}", headers=headers, files={"file": (name, blob if blob is not None else _png(), ctype)},
    )


def _media_path(image_id):
    return f"/api/v1/media/site-images/{image_id}"


async def test_upload_is_served_publicly_as_reencoded_jpeg(client):
    headers, _ = await _setup(client, "Img Farm A", "img1@example.com")
    up = await _upload(client, headers, kind="logo")
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["kind"] == "logo" and body["url"] is None  # database backend: served by the API itself

    served = await client.get(_media_path(body["id"]))  # no auth header
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(served.content)).format == "JPEG"
    assert (await client.get(_media_path("00000000-0000-0000-0000-000000000000"))).status_code == 404


async def test_uploaded_url_works_in_profile_and_banner_and_banner_delete_removes_file(client):
    headers, slug = await _setup(client, "Img Farm B", "img2@example.com")
    image_id = (await _upload(client, headers)).json()["id"]
    url = f"http://localhost:8000{_media_path(image_id)}"

    created = await client.post("/api/v1/cms/banners", headers=headers, json={"title": "Sale", "image_url": url})
    assert created.status_code == 201
    banner_id = created.json()["id"]
    assert [b["image_url"] for b in (await client.get(f"/api/v1/public/{slug}/banners")).json()] == [url]

    deleted = await client.delete(f"/api/v1/cms/banners/{banner_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/cms/banners", headers=headers)).json() == []
    assert (await client.get(f"/api/v1/public/{slug}/banners")).json() == []
    assert (await client.get(_media_path(image_id))).status_code == 404  # its uploaded file went with it


async def test_deleting_banner_keeps_image_still_used_as_logo(client):
    headers, _ = await _setup(client, "Img Farm C", "img3@example.com")
    image_id = (await _upload(client, headers)).json()["id"]
    url = f"http://localhost:8000{_media_path(image_id)}"
    await client.put("/api/v1/cms/profile", headers=headers, json={"logo_url": url})
    banner_id = (await client.post("/api/v1/cms/banners", headers=headers, json={"title": "B", "image_url": url})).json()["id"]

    await client.delete(f"/api/v1/cms/banners/{banner_id}", headers=headers)
    assert (await client.get(_media_path(image_id))).status_code == 200


async def test_replacing_logo_releases_old_upload(client):
    headers, _ = await _setup(client, "Img Farm D", "img4@example.com")
    first = (await _upload(client, headers, kind="logo")).json()["id"]
    second = (await _upload(client, headers, kind="logo")).json()["id"]
    await client.put("/api/v1/cms/profile", headers=headers, json={"logo_url": f"http://x{_media_path(first)}"})
    await client.put("/api/v1/cms/profile", headers=headers, json={"logo_url": f"http://x{_media_path(second)}"})
    assert (await client.get(_media_path(first))).status_code == 404
    assert (await client.get(_media_path(second))).status_code == 200


async def test_pasted_external_urls_still_work_and_are_untouched(client):
    headers, _ = await _setup(client, "Img Farm E", "img5@example.com")
    ext = "https://example.com/banner.jpg"
    banner_id = (await client.post("/api/v1/cms/banners", headers=headers, json={"title": "Ext", "image_url": ext})).json()["id"]
    assert (await client.delete(f"/api/v1/cms/banners/{banner_id}", headers=headers)).status_code == 204


async def test_validation_and_permissions(client):
    headers, _ = await _setup(client, "Img Farm F", "img6@example.com")
    assert (await _upload(client, headers, blob=b"not an image", name="x.png")).status_code == 422
    assert (await _upload(client, headers, blob=b"")).status_code == 422
    assert (await client.post("/api/v1/cms/images?kind=avatar", headers=headers,
                              files={"file": ("a.png", _png(), "image/png")})).status_code == 422
    assert (await client.post("/api/v1/cms/images?kind=logo", files={"file": ("a.png", _png(), "image/png")})).status_code in (401, 403)
    assert (await client.delete("/api/v1/cms/banners/00000000-0000-0000-0000-000000000000")).status_code in (401, 403)
    assert (await client.delete("/api/v1/cms/banners/00000000-0000-0000-0000-000000000000", headers=headers)).status_code == 404


async def test_cannot_delete_another_orgs_banner(client):
    a, _ = await _setup(client, "Img Farm G", "img7@example.com")
    b, _ = await _setup(client, "Img Farm H", "img8@example.com")
    banner_id = (await client.post("/api/v1/cms/banners", headers=a, json={"title": "A", "image_url": "https://e.com/a.jpg"})).json()["id"]
    assert (await client.delete(f"/api/v1/cms/banners/{banner_id}", headers=b)).status_code == 404
    assert len((await client.get("/api/v1/cms/banners", headers=a)).json()) == 1


async def test_bucket_backend_returns_cdn_url_and_banner_delete_removes_the_object(client, monkeypatch):
    from test_listing_images_supabase import PUBLIC, _enable_bucket  # in-memory fake Supabase Storage, no network
    bucket = _enable_bucket(monkeypatch)
    headers, _ = await _setup(client, "Img Farm Bucket", "img9@example.com")

    up = (await _upload(client, headers)).json()
    assert up["url"].startswith(PUBLIC) and up["url"].removeprefix(PUBLIC) in bucket.objects
    assert "/site/" in up["url"]
    served = await client.get(_media_path(up["id"]), follow_redirects=False)
    assert served.status_code == 302 and served.headers["location"] == up["url"]

    media_url = f"http://localhost:8000{_media_path(up['id'])}"  # what the widget stores
    banner_id = (await client.post("/api/v1/cms/banners", headers=headers, json={"title": "B", "image_url": media_url})).json()["id"]
    await client.delete(f"/api/v1/cms/banners/{banner_id}", headers=headers)
    assert bucket.objects == {} and up["url"].removeprefix(PUBLIC) in bucket.deleted
    assert (await client.get(_media_path(up["id"]), follow_redirects=False)).status_code == 404
