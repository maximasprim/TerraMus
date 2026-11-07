"""A login ends after a period with no activity (SESSION_IDLE_TIMEOUT_MINUTES, default 60), enforced on the server.

  * a refresh token issued now lasts the inactivity window (not 30 days) and every renewal slides it forward
  * a login not renewed within the window can no longer be renewed (it must sign in again) - including a login
    issued before the limit existed
  * activity inside the window keeps the person signed in
  * 0 switches the limit off (the old 30-day behaviour); tiny values are raised to 20 minutes
  * /auth/me tells the web app the limit so it can warn and sign out
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core import security
from tests.test_platform_admin import _register_org

pytestmark = pytest.mark.asyncio


async def _login(client, email, org):
    await _register_org(client, org, email)
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    assert r.status_code == 200, r.text
    return r.json()


async def _age_tokens(engine, minutes):
    async with engine.begin() as c:
        await c.execute(text("UPDATE refresh_tokens SET created_at = created_at - make_interval(mins => :m)"), {"m": minutes})


def test_lifetime_and_floor(monkeypatch):
    monkeypatch.setattr(security.settings, "SESSION_IDLE_TIMEOUT_MINUTES", 60)
    assert security.idle_timeout_minutes() == 60 and security.refresh_token_lifetime() == timedelta(minutes=60)
    monkeypatch.setattr(security.settings, "SESSION_IDLE_TIMEOUT_MINUTES", 5)
    assert security.idle_timeout_minutes() == security.MIN_IDLE_TIMEOUT_MINUTES        # raised to the floor
    monkeypatch.setattr(security.settings, "SESSION_IDLE_TIMEOUT_MINUTES", 0)
    assert security.idle_timeout_minutes() == 0
    assert security.refresh_token_lifetime() == timedelta(days=security.settings.REFRESH_TOKEN_EXPIRE_DAYS)
    monkeypatch.setattr(security.settings, "SESSION_IDLE_TIMEOUT_MINUTES", 10_000_000)  # never longer than the old cap
    assert security.refresh_token_lifetime() == timedelta(days=security.settings.REFRESH_TOKEN_EXPIRE_DAYS)


async def test_me_reports_the_limit(client, engine):
    tok = await _login(client, "idle1@example.com", "Idle Farm 1")
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert me.json()["idle_timeout_minutes"] == 60


async def test_new_refresh_token_expires_in_the_window_not_30_days(client, engine):
    await _login(client, "idle2@example.com", "Idle Farm 2")
    async with engine.begin() as c:
        exp = (await c.execute(text("SELECT expires_at FROM refresh_tokens ORDER BY created_at DESC LIMIT 1"))).scalar_one()
    left = exp - datetime.now(timezone.utc)
    assert timedelta(minutes=58) < left <= timedelta(minutes=60)


async def test_activity_within_the_window_keeps_the_login_and_slides_it(client, engine):
    tok = await _login(client, "idle3@example.com", "Idle Farm 3")
    await _age_tokens(engine, 40)                                   # 40 minutes since the last renewal: still inside 60
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200, r.text
    await _age_tokens(engine, 40)                                   # the renewed token slides: another 40 minutes is fine
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert r2.status_code == 200, r2.text


async def test_a_login_idle_past_the_window_cannot_be_renewed(client, engine):
    tok = await _login(client, "idle4@example.com", "Idle Farm 4")
    await _age_tokens(engine, 61)
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401, r.text
    again = await client.post("/api/v1/auth/login", json={"email": "idle4@example.com", "password": "supersecret123"})
    assert again.status_code == 200                                 # signing in again works


async def test_a_login_issued_before_the_limit_existed_is_also_cut_off(client, engine):
    tok = await _login(client, "idle5@example.com", "Idle Farm 5")
    async with engine.begin() as c:                                 # an old-style token: 30-day expiry, created long ago
        await c.execute(text("UPDATE refresh_tokens SET created_at = now() - interval '3 days', expires_at = now() + interval '27 days'"))
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401


async def test_zero_turns_the_limit_off(client, engine, monkeypatch):
    monkeypatch.setattr(security.settings, "SESSION_IDLE_TIMEOUT_MINUTES", 0)
    tok = await _login(client, "idle6@example.com", "Idle Farm 6")
    await _age_tokens(engine, 60 * 24 * 3)
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200, r.text
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["idle_timeout_minutes"] == 0
