"""Thin client for Vercel's Domains API — assigning a tenant's custom
domain to this project so Vercel serves it (TLS included, automatically)
alongside every other domain already on the project.

Same caveat every external-API integration in this codebase carries
(payments/providers/mpesa.py, billing/pdf.py): written against Vercel's
documented API shape, not exercised against a live account — this sandbox
has no network access. Verify against a real `VERCEL_API_TOKEN` before
relying on it.

Two DIFFERENT kinds of "verified" matter here, and this module is only
responsible for one of them:
- Vercel's own domain verification (this module) — whether Vercel's edge
  network has confirmed enough DNS control to safely start routing/TLS for
  the domain. Vercel handles this however it needs to; `get_domain_status`
  just reports what Vercel says.
- This app's OWN domain_verified flag (identity/service.py) — an
  independent DNS TXT record check proving the org that ADDED the domain
  in our UI actually controls it, checked before we ever treat incoming
  requests for that Host header as belonging to that org. Vercel serving
  the domain and our own ownership check passing are separate facts; both
  must be true before a tenant's storefront is reachable at their domain.
"""
import httpx

from app.core.config import get_settings

VERCEL_API_BASE = "https://api.vercel.com"


def _configured() -> bool:
    settings = get_settings()
    return bool(settings.VERCEL_API_TOKEN and settings.VERCEL_PROJECT_ID)


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    return {"Authorization": f"Bearer {settings.VERCEL_API_TOKEN}"}


def _team_params() -> dict[str, str]:
    settings = get_settings()
    return {"teamId": settings.VERCEL_TEAM_ID} if settings.VERCEL_TEAM_ID else {}


class VercelNotConfigured(Exception):
    """Raised when VERCEL_API_TOKEN/VERCEL_PROJECT_ID aren't set — the
    custom-domains feature is entirely opt-in (see config.py), so callers
    should catch this and surface a clear "not enabled" error rather than
    a raw connection failure."""


async def add_domain_to_project(domain: str) -> dict:
    """POST /v10/projects/{project}/domains — registers the domain against
    this Vercel project. Idempotent in practice: re-adding a domain already
    on the project returns its current state rather than erroring, per
    Vercel's documented behavior."""
    if not _configured():
        raise VercelNotConfigured()
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{VERCEL_API_BASE}/v10/projects/{settings.VERCEL_PROJECT_ID}/domains",
            headers=_auth_headers(), params=_team_params(), json={"name": domain},
        )
        resp.raise_for_status()
        return resp.json()


async def get_domain_status(domain: str) -> dict:
    """GET /v9/projects/{project}/domains/{domain} — current verification/
    config state Vercel has for this domain (includes `verified`, and a
    `verification` array of {type, domain, value} challenges if Vercel
    still needs something published before it'll route traffic)."""
    if not _configured():
        raise VercelNotConfigured()
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{VERCEL_API_BASE}/v9/projects/{settings.VERCEL_PROJECT_ID}/domains/{domain}",
            headers=_auth_headers(), params=_team_params(),
        )
        resp.raise_for_status()
        return resp.json()


async def remove_domain_from_project(domain: str) -> None:
    """DELETE /v9/projects/{project}/domains/{domain}."""
    if not _configured():
        raise VercelNotConfigured()
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(
            f"{VERCEL_API_BASE}/v9/projects/{settings.VERCEL_PROJECT_ID}/domains/{domain}",
            headers=_auth_headers(), params=_team_params(),
        )
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
