"""Pure, dependency-free security helpers (no FastAPI/pydantic imports, so
they're trivially unit-testable and safe to import from config-adjacent code).

Two concerns live here:
  * whether the *mock* payment provider may run in this environment, and
  * how to determine the real client IP behind a reverse proxy/load balancer.
"""
from __future__ import annotations

# Environments where relaxed dev conveniences (mock payments) are acceptable.
# ANY other ENV value (production, prod, staging, aws...) is treated as
# production-like - fail closed rather than open.
NON_PRODUCTION_ENVS = frozenset({"development", "dev", "local", "test", "testing"})

# Placeholder secrets that ship in this repo's config.py / .env.example /
# k8s template. Anyone can read them, so they must never protect a live system.
INSECURE_SECRETS = frozenset({
    "mock-payment-secret-change-me",
    "replace-with-a-long-random-value",
    "REPLACE_WITH_A_REAL_SECRET",
    "change-me-in-env",
    "",
})

MIN_STRONG_SECRET_LENGTH = 24


def is_production_like(env: str) -> bool:
    return (env or "").strip().lower() not in NON_PRODUCTION_ENVS


def mock_payments_enabled(env: str, allow_mock: bool | None, mock_secret: str) -> bool:
    """The mock provider marks orders as paid without any real money moving,
    and its webhook is authenticated only by an HMAC over MOCK_PAYMENT_SECRET.

    - allow_mock is False            -> always off.
    - non-production ENV             -> on (dev/test convenience, unchanged).
    - production-like ENV            -> on ONLY if explicitly allowed AND the
      secret is not a published placeholder and is reasonably long.
    """
    if allow_mock is False:
        return False
    if not is_production_like(env):
        return True
    return (
        allow_mock is True
        and mock_secret not in INSECURE_SECRETS
        and len(mock_secret) >= MIN_STRONG_SECRET_LENGTH
    )


def daraja_warnings(env: str, daraja_env: str, consumer_key: str, callback_url: str, callback_secret: str) -> list[str]:
    """Warnings for a production-like deployment that has M-Pesa credentials configured. Nothing is reported when
    no Daraja credentials are set (M-Pesa is simply not in use)."""
    import re
    if not is_production_like(env) or not consumer_key:
        return []
    out: list[str] = []
    if (daraja_env or "").strip().lower() != "production":
        out.append("DARAJA_ENV is not 'production': STK prompts go to Safaricom's SANDBOX and no real money moves. "
                   "Set DARAJA_ENV=production with live credentials.")
    if not callback_url.lower().startswith("https://"):
        out.append("DARAJA_CALLBACK_URL is not an https:// address. Safaricom will not deliver payment confirmations to it.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,}", callback_secret or ""):
        out.append("DARAJA_CALLBACK_SHARED_SECRET is missing, shorter than 24 characters, or has characters that are not "
                   "URL-safe. Payment confirmations will be refused. Use 24+ letters, digits, '-' or '_'.")
    return out


def security_warnings(env: str, jwt_secret: str, mock_secret: str, allow_mock: bool | None) -> list[str]:
    """Human-readable startup warnings. Deliberately warnings, not exceptions:
    refusing to boot could take down an existing deployment, whereas a loud
    log line is visible without changing behaviour."""
    warnings: list[str] = []
    if not is_production_like(env):
        return warnings
    if jwt_secret in INSECURE_SECRETS or len(jwt_secret) < 32:
        warnings.append(
            "JWT_SECRET is a placeholder or shorter than 32 characters - anyone who can "
            "read the repo can forge login tokens. Set a long random JWT_SECRET."
        )
    if allow_mock is True and not mock_payments_enabled(env, allow_mock, mock_secret):
        warnings.append(
            "ALLOW_MOCK_PAYMENTS=true but MOCK_PAYMENT_SECRET is a placeholder/too short, "
            "so the mock payment provider stays DISABLED. Set a strong secret or disable it."
        )
    return warnings


def resolve_client_ip(forwarded_for: str | None, peer: str | None, trusted_proxies: int) -> str:
    """Return the client IP for rate-limiting.

    `trusted_proxies` = how many reverse proxies/load balancers sit in front of
    the API and append to X-Forwarded-For (0 = none, trust only the socket
    peer - the safe default, and the previous behaviour). Each trusted proxy
    appends the address it *received the connection from*, so the entry
    `trusted_proxies` positions from the right is the real client; anything to
    its left is client-supplied and spoofable, so it is ignored.
    """
    fallback = peer or "unknown"
    if trusted_proxies <= 0 or not forwarded_for:
        return fallback
    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    if len(parts) < trusted_proxies:
        return fallback  # header shorter than expected: misconfiguration or spoof - don't trust it
    return parts[-trusted_proxies]
