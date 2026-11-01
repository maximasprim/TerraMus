"""The permission cache is opt-in, keyed by the user's role ids, and never serves a different role set's answer."""
import uuid
from types import SimpleNamespace as NS

import pytest

from app.modules.identity import service

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, codes): self._codes = codes
    def scalars(self): return self
    def all(self): return list(self._codes)


class _FakeDb:
    def __init__(self, codes): self.calls, self._codes = 0, codes
    async def execute(self, _q):
        self.calls += 1
        return _Result(self._codes)


def _user(*role_ids): return NS(roles=[NS(id=r) for r in role_ids])


async def test_off_by_default_every_call_reads_the_database(monkeypatch):
    monkeypatch.delenv("PERMISSION_CACHE_TTL_SECONDS", raising=False)
    service.invalidate_permission_cache()
    db, u = _FakeDb(["a.read"]), _user(uuid.uuid4())
    assert await service.get_user_permissions(db, u) == {"a.read"}
    assert await service.get_user_permissions(db, u) == {"a.read"}
    assert db.calls == 2


async def test_enabled_cache_reuses_the_answer_but_a_role_change_is_seen_at_once(monkeypatch):
    monkeypatch.setenv("PERMISSION_CACHE_TTL_SECONDS", "60")
    service.invalidate_permission_cache()
    r1, r2 = uuid.uuid4(), uuid.uuid4()
    db = _FakeDb(["a.read"])
    assert await service.get_user_permissions(db, _user(r1)) == {"a.read"}
    assert await service.get_user_permissions(db, _user(r1)) == {"a.read"}
    assert db.calls == 1                                            # second call served from the cache
    db._codes = ["b.write"]
    assert await service.get_user_permissions(db, _user(r2)) == {"b.write"}     # different roles -> different key
    assert await service.get_user_permissions(db, _user(r1)) == {"a.read"}      # r1 unchanged within the TTL
    service.invalidate_permission_cache()
    assert await service.get_user_permissions(db, _user(r1)) == {"b.write"}     # explicit invalidation forces a re-read
    assert await service.get_user_permissions(db, NS(roles=[])) == set()        # no roles -> no permissions, no query


async def test_callers_cannot_corrupt_the_cache(monkeypatch):
    monkeypatch.setenv("PERMISSION_CACHE_TTL_SECONDS", "60")
    service.invalidate_permission_cache()
    db, u = _FakeDb(["a.read"]), _user(uuid.uuid4())
    first = await service.get_user_permissions(db, u)
    first.add("admin.everything")                                   # a caller mutating its copy
    assert await service.get_user_permissions(db, u) == {"a.read"}