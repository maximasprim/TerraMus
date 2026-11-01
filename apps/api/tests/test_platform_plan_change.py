"""A superadmin can move a tenant to another plan from the platform dashboard (no payment)."""
import pytest
from sqlalchemy import text

from tests.test_platform_admin import _make_platform_admin, _platform_login, _register_org

pytestmark = pytest.mark.asyncio


async def _org_id(client, headers, name):
    orgs = await client.get("/api/v1/platform/organizations", headers=headers)
    return next(o["id"] for o in orgs.json() if o["name"] == name)


async def test_superadmin_changes_a_tenants_plan(client, engine):
    await _make_platform_admin(engine)
    tenant = await _register_org(client, "Plan Farm", "plan@example.com")
    h = {"Authorization": f"Bearer {await _platform_login(client)}"}
    th = {"Authorization": f"Bearer {tenant['access_token']}"}
    oid = await _org_id(client, h, "Plan Farm")

    plans = (await client.get("/api/v1/platform/billing/tiers", headers=h)).json()
    assert {"free", "basic", "pro", "enterprise"} <= {p["slug"] for p in plans}

    r = await client.patch(f"/api/v1/platform/organizations/{oid}/subscription", json={"tier_slug": "pro"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["subscription_tier"] == "Pro" and r.json()["subscription_status"] == "active"
    assert r.json()["subscription_tier_slug"] == "pro" and r.json()["subscription_period_end"]

    mine = (await client.get("/api/v1/billing/subscription", headers=th)).json()      # the tenant sees the new plan
    assert mine["tier"]["slug"] == "pro" and mine["status"] == "active"

    async with engine.connect() as c:                                                   # audited exactly once
        n = (await c.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'organization.subscription_change'"))).scalar_one()
    assert n == 1


async def test_unknown_plan_and_over_limit_plan_are_refused(client, engine):
    await _make_platform_admin(engine)
    await _register_org(client, "Limit Farm", "limit@example.com")
    h = {"Authorization": f"Bearer {await _platform_login(client)}"}
    oid = await _org_id(client, h, "Limit Farm")
    url = f"/api/v1/platform/organizations/{oid}/subscription"

    assert (await client.patch(url, json={"tier_slug": "platinum"}, headers=h)).status_code == 422
    assert (await client.patch(url, json={"tier_slug": "pro", "status": "bogus"}, headers=h)).status_code == 422

    async with engine.begin() as c:                                                     # pretend Free allows no users at all
        await c.execute(text("UPDATE subscription_tiers SET max_users = 0 WHERE slug = 'free'"))
    refused = await client.patch(url, json={"tier_slug": "free"}, headers=h)
    assert refused.status_code == 400 and "users" in refused.json()["detail"]