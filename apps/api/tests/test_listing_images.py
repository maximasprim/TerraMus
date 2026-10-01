"""Multiple photos per listing: upload, ordering, public exposure, media
serving, validation, tenant isolation."""
import io

import pytest
from PIL import Image

from app.modules.commerce import images as image_limits

pytestmark = pytest.mark.asyncio


def _jpeg(width=800, height=600, color=(30, 120, 60), exif_make: str | None = None) -> bytes:
    buf = io.BytesIO()
    kwargs = {}
    if exif_make:
        exif = Image.Exif()
        exif[0x010F] = exif_make
        kwargs["exif"] = exif.tobytes()
    Image.new("RGB", (width, height), color).save(buf, "JPEG", **kwargs)
    return buf.getvalue()


def _files(*blobs, name="photo"):
    return [("files", (f"{name}{i}.jpg", blob, "image/jpeg")) for i, blob in enumerate(blobs)]


async def _setup(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner", "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_slug = (await client.get("/api/v1/auth/me", headers=headers)).json()["organization"]["slug"]

    farm_id = (await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)).json()["id"]
    branch_id = (await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "B"}, headers=headers)).json()["id"]
    loc_id = (await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "Paddock 1", "location_type": "paddock"}, headers=headers,
    )).json()["id"]
    animal_id = (await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "IMG-COW", "species": "cattle",
        "breed": "Friesian", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })).json()["id"]
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    listing = (await client.post("/api/v1/listings", headers=headers, json={
        "animal_id": animal_id, "title": "Friesian Cow", "pricing_type": "fixed", "price": "85000",
    })).json()
    return headers, org_slug, listing


async def test_upload_multiple_photos_assigns_positions_in_order(client):
    headers, _, listing = await _setup(client, "Img Farm A", "img1@example.com")
    resp = await client.post(
        f"/api/v1/listings/{listing['id']}/images", headers=headers,
        files=_files(_jpeg(color=(255, 0, 0)), _jpeg(color=(0, 255, 0)), _jpeg(color=(0, 0, 255))),
    )
    assert resp.status_code == 201
    assert [i["position"] for i in resp.json()] == [0, 1, 2]

    listed = await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)
    assert [i["id"] for i in listed.json()] == [i["id"] for i in resp.json()]

    more = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg()))
    assert more.json()[0]["position"] == 3  # appended after the existing photos


async def test_public_listing_exposes_photo_ids_cover_first_on_list_and_detail(client):
    headers, org_slug, listing = await _setup(client, "Img Farm B", "img2@example.com")
    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg()))
    ids = [i["id"] for i in up.json()]

    public_list = (await client.get(f"/api/v1/public/{org_slug}/listings")).json()
    assert [i["id"] for i in public_list[0]["images"]] == ids

    detail = (await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")).json()
    assert [i["id"] for i in detail["images"]] == ids


async def test_listing_without_photos_has_empty_images_list(client):
    _, org_slug, listing = await _setup(client, "Img Farm C", "img3@example.com")
    detail = (await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")).json()
    assert detail["images"] == []


async def test_media_endpoint_serves_full_and_thumbnail_publicly_with_long_cache(client):
    headers, _, listing = await _setup(client, "Img Farm D", "img4@example.com")
    up = await client.post(
        f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(3000, 2000)),
    )
    image_id = up.json()[0]["id"]

    full = await client.get(f"/api/v1/media/listing-images/{image_id}")  # no auth header
    thumb = await client.get(f"/api/v1/media/listing-images/{image_id}/thumb")
    assert full.status_code == thumb.status_code == 200
    assert full.headers["content-type"] == "image/jpeg"
    assert "immutable" in full.headers["cache-control"]
    assert max(Image.open(io.BytesIO(full.content)).size) == image_limits.FULL_MAX_EDGE
    assert max(Image.open(io.BytesIO(thumb.content)).size) == image_limits.THUMB_MAX_EDGE
    assert len(thumb.content) < len(full.content)

    missing = await client.get("/api/v1/media/listing-images/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_uploaded_photo_metadata_such_as_camera_make_is_stripped(client):
    headers, _, listing = await _setup(client, "Img Farm E", "img5@example.com")
    blob = _jpeg(exif_make="SecretCamera")
    assert b"SecretCamera" in blob
    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(blob))
    served = await client.get(f"/api/v1/media/listing-images/{up.json()[0]['id']}")
    assert b"SecretCamera" not in served.content


async def test_non_image_and_svg_uploads_are_rejected_and_nothing_is_stored(client):
    headers, _, listing = await _setup(client, "Img Farm F", "img6@example.com")
    bad = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=[
        ("files", ("evil.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "image/jpeg")),
    ])
    assert bad.status_code == 422

    # one good + one bad file: the whole request is rejected, the good one is NOT saved
    mixed = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=[
        ("files", ("ok.jpg", _jpeg(), "image/jpeg")), ("files", ("bad.jpg", b"not an image", "image/jpeg")),
    ])
    assert mixed.status_code == 422
    assert (await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)).json() == []


async def test_photo_count_is_capped_per_listing(client):
    headers, _, listing = await _setup(client, "Img Farm G", "img7@example.com")
    cap = image_limits.MAX_IMAGES_PER_LISTING
    ok = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(*[_jpeg(64, 64)] * cap))
    assert ok.status_code == 201
    over = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(64, 64)))
    assert over.status_code == 409


async def test_delete_closes_the_gap_and_promotes_next_photo_to_cover(client):
    headers, _, listing = await _setup(client, "Img Farm H", "img8@example.com")
    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg(), _jpeg()))
    first, second, third = [i["id"] for i in up.json()]

    assert (await client.delete(f"/api/v1/listings/{listing['id']}/images/{first}", headers=headers)).status_code == 204
    remaining = (await client.get(f"/api/v1/listings/{listing['id']}/images", headers=headers)).json()
    assert [(i["id"], i["position"]) for i in remaining] == [(second, 0), (third, 1)]

    gone = await client.delete(f"/api/v1/listings/{listing['id']}/images/{first}", headers=headers)
    assert gone.status_code == 404


async def test_reorder_changes_cover_and_rejects_incomplete_or_duplicate_lists(client):
    headers, org_slug, listing = await _setup(client, "Img Farm I", "img9@example.com")
    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg(), _jpeg()))
    a, b, c = [i["id"] for i in up.json()]

    ok = await client.put(f"/api/v1/listings/{listing['id']}/images/order", headers=headers, json={"image_ids": [c, a, b]})
    assert ok.status_code == 200 and [i["id"] for i in ok.json()] == [c, a, b]
    public = (await client.get(f"/api/v1/public/{org_slug}/listings/{listing['slug']}")).json()
    assert public["images"][0]["id"] == c  # new cover is what shoppers see first

    missing = await client.put(f"/api/v1/listings/{listing['id']}/images/order", headers=headers, json={"image_ids": [a, b]})
    dup = await client.put(f"/api/v1/listings/{listing['id']}/images/order", headers=headers, json={"image_ids": [a, a, b]})
    assert missing.status_code == 400 and dup.status_code == 400


async def test_admin_listing_grid_reports_cover_and_count(client):
    headers, _, listing = await _setup(client, "Img Farm J", "img10@example.com")
    before = (await client.get("/api/v1/listings", headers=headers)).json()[0]
    assert before["cover_image_id"] is None and before["image_count"] == 0

    up = await client.post(f"/api/v1/listings/{listing['id']}/images", headers=headers, files=_files(_jpeg(), _jpeg()))
    after = (await client.get("/api/v1/listings", headers=headers)).json()[0]
    assert after["cover_image_id"] == up.json()[0]["id"] and after["image_count"] == 2


async def test_photos_require_authentication_and_are_tenant_isolated(client):
    headers_a, _, listing_a = await _setup(client, "Img Farm K", "img11@example.com")
    headers_b, _, _ = await _setup(client, "Img Farm L", "img12@example.com")
    up = await client.post(f"/api/v1/listings/{listing_a['id']}/images", headers=headers_a, files=_files(_jpeg()))
    image_id = up.json()[0]["id"]

    assert (await client.post(f"/api/v1/listings/{listing_a['id']}/images", files=_files(_jpeg()))).status_code == 401
    # org B can neither see, add to, nor delete org A's photos
    assert (await client.get(f"/api/v1/listings/{listing_a['id']}/images", headers=headers_b)).status_code == 404
    assert (await client.post(f"/api/v1/listings/{listing_a['id']}/images", headers=headers_b, files=_files(_jpeg()))).status_code == 404
    assert (await client.delete(f"/api/v1/listings/{listing_a['id']}/images/{image_id}", headers=headers_b)).status_code == 404
    assert len((await client.get(f"/api/v1/listings/{listing_a['id']}/images", headers=headers_a)).json()) == 1
