import pytest

from app.core.middleware import RedisRateLimiter

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    """Minimal stand-in for redis.asyncio.Redis covering exactly the two
    calls RedisRateLimiter makes (incr, expire) - enough to prove the
    fixed-window counting logic itself is correct without needing a real
    Redis server reachable from this sandbox/CI environment."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass  # TTL behavior isn't exercised by this test - only the count logic is


async def test_redis_rate_limiter_blocks_after_threshold():
    limiter = RedisRateLimiter(max_requests=3, window_seconds=60, redis_url="redis://unused")
    fake = _FakeRedis()
    limiter._client = fake  # inject the fake in place of a lazily-created real client

    for _ in range(3):
        await limiter.check("test-key")  # should not raise

    with pytest.raises(Exception) as exc_info:
        await limiter.check("test-key")
    assert "429" in str(exc_info.value) or "Too many" in str(exc_info.value)


async def test_redis_rate_limiter_keys_are_independent():
    limiter = RedisRateLimiter(max_requests=1, window_seconds=60, redis_url="redis://unused")
    fake = _FakeRedis()
    limiter._client = fake

    await limiter.check("key-a")  # consumes key-a's one allowed hit
    await limiter.check("key-b")  # a different key must not be affected by key-a's count
