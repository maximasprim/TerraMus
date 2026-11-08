"""Adding an animal's photo and recording its weight have their own ticks, separate from livestock.update."""
import io
import pytest

from app.modules.identity.permissions import DEFAULT_ROLE_GRANTS
from tests.test_roles_management import _owner, _roles, _staff

pytestmark = pytest.mark.asyncio


def _png() -> bytes:
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (40, 40), (10, 120, 30)).save(b, "PNG"); return b.getvalue()


async def _animal(client, h) -> str:
    farm = (await client.post("/api/v1/farms", json={"name": "Main"}, headers=h)).json()
    r = await client.post("/api/v1/livestock", headers=h, json={
        "farm_id": farm["id"], "species": "cattle", "sex": "male", "animal_number": "P-001", "acquisition_date": "2026-01-01", "acquisition_method": "purchased"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_defaults_keep_everyone_who_could_update():
    for name, grants in DEFAULT_ROLE_GRANTS.items():
        if "livestock.update" in grants:
            assert {"livestock.photo", "livestock.weigh"} <= set(grants), name
    assert not {"livestock.photo", "livestock.weigh"} & set(DEFAULT_ROLE_GRANTS["Field Recorder"])


async def test_recorder_can_be_given_photo_and_weight_without_update(client, engine):
    h = await _owner(client, "Photo Farm", "photo@example.com")
    animal = await _animal(client, h)
    roles = await _roles(client, h)
    rec = roles["Field Recorder"]
    worker = await _staff(client, h, rec["id"], "rec-photo@example.com")
    photo = lambda: client.put(f"/api/v1/livestock/{animal}/photo", headers=worker, files={"file": ("a.png", _png(), "image/png")})
    weigh = lambda: client.post(f"/api/v1/livestock/{animal}/weights", headers=worker, json={"weight_kg": "250"})

    # by default the recorder can do neither (as before)
    assert (await photo()).status_code == 403 and (await weigh()).status_code == 403

    # tick photo only
    r = await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": rec["permissions"] + ["livestock.photo"]})
    assert r.status_code == 200, r.text
    assert (await photo()).status_code in (200, 201, 204)
    assert (await weigh()).status_code == 403

    # tick weight too - still cannot edit the animal or change its status, or remove the photo
    r = await client.put(f"/api/v1/roles/{rec['id']}", headers=h, json={"permissions": rec["permissions"] + ["livestock.photo", "livestock.weigh"]})
    assert r.status_code == 200
    assert (await weigh()).status_code == 201
    assert (await client.patch(f"/api/v1/livestock/{animal}", headers=worker, json={"name": "x"})).status_code == 403
    assert (await client.post(f"/api/v1/livestock/{animal}/status", headers=worker, json={"status": "quarantined"})).status_code == 403
    assert (await client.delete(f"/api/v1/livestock/{animal}/photo", headers=worker)).status_code == 403


async def test_roles_that_could_update_still_can(client, engine):
    h = await _owner(client, "Photo Farm B", "photob@example.com")
    animal = await _animal(client, h)
    assert (await client.put(f"/api/v1/livestock/{animal}/photo", headers=h, files={"file": ("a.png", _png(), "image/png")})).status_code in (200, 201, 204)
    assert (await client.post(f"/api/v1/livestock/{animal}/weights", headers=h, json={"weight_kg": "300"})).status_code == 201
    roles = await _roles(client, h)
    assert {"livestock.photo", "livestock.weigh"} <= set(roles["Livestock Manager"]["permissions"])
    assert not {"livestock.photo", "livestock.weigh"} & set(roles["Veterinarian"]["permissions"])
