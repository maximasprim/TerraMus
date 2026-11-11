"""Which weigh form a role sees: 'weighform.multi' = several animals at once; without it, one animal at a time."""
import pytest

from tests.test_field_recorder_role import _grants, _owner, _recorder

pytestmark = pytest.mark.asyncio


async def _perms(client, h):
    return set((await client.get("/api/v1/auth/me", headers=h)).json()["permissions"])


async def test_field_recorder_gets_the_one_at_a_time_form_and_other_roles_keep_the_full_form(client, engine):
    h, _ = await _owner(client, "Form Farm", "formowner@example.com")
    rec = await _recorder(client, h, "formrec@example.com")
    assert "feedlot.weigh" in await _perms(client, rec) and "weighform.multi" not in await _perms(client, rec)
    assert "weighform.multi" in await _perms(client, h)                                   # the owner holds every permission
    for role in ("Farm Manager", "Livestock Manager", "Farm Worker"):
        assert "weighform.multi" in await _grants(engine, "Form Farm", role), role
    assert "weighform.multi" not in await _grants(engine, "Form Farm", "Field Recorder")
    assert "weighform.multi" not in await _grants(engine, "Form Farm", "Veterinarian")    # cannot weigh at all


async def test_the_owner_can_switch_the_form_for_a_role(client, engine):
    h, _ = await _owner(client, "Form Farm 2", "formowner2@example.com")
    rec = await _recorder(client, h, "formrec2@example.com")
    roles = (await client.get("/api/v1/roles", headers=h)).json()
    fr = next(r for r in roles if r["name"] == "Field Recorder")
    r = await client.put(f"/api/v1/roles/{fr['id']}", headers=h, json={"permissions": sorted(set(fr["permissions"]) | {"weighform.multi"})})
    assert r.status_code == 200, r.text
    assert "weighform.multi" in await _perms(client, rec)                                 # takes effect straight away
    cat = (await client.get("/api/v1/roles/catalog", headers=h)).json()
    assert any(p["code"] == "weighform.multi" and p["group_label"] == "Weigh form" for p in cat["permissions"])
