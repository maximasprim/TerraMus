"""Strict validation of tenant-supplied custom domains (pure, no app imports).

The domain string is stored, sent to the Vercel API, interpolated into a DNS
TXT lookup (`_farmplatform-verify.<domain>`) and later matched against the
request Host header - so it must be a plain, real hostname. It used to be
checked for length only, so `https://farm.com/path`, `*.farm.com`, an IP address
or `localhost` were all accepted and then failed confusingly downstream.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TLD = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")
_FORBIDDEN_CHARS = set("/?#@: \t\r\n*_\\")

# Hosts/suffixes a tenant must never be able to claim: platform-owned or non-routable.
_RESERVED_SUFFIXES = ("vercel.app", "localhost", "local", "internal", "invalid")


def normalise_domain(raw: str, reserved_hosts: tuple[str, ...] | list[str] = ()) -> str:
    """Return the canonical lowercase hostname or raise ValueError with a
    message that is safe to show to the user."""
    domain = (raw or "").strip().lower().rstrip(".")
    if not domain:
        raise ValueError("Enter a domain like farm.example.com")
    if "://" in domain or _FORBIDDEN_CHARS & set(domain):
        raise ValueError("Enter just the domain name (like farm.example.com) - no https://, path, port or wildcard")
    if len(domain) > 253:
        raise ValueError("That domain name is too long")
    if re.fullmatch(r"[\d.]+", domain):
        raise ValueError("Enter a domain name, not an IP address")
    labels = domain.split(".")
    if len(labels) < 2:
        raise ValueError("A full domain needs at least two parts, like farm.example.com")
    if not all(_LABEL.match(label) for label in labels):
        raise ValueError("That doesn't look like a valid domain name")
    if not _TLD.match(labels[-1]):
        raise ValueError("That domain doesn't end in a valid extension like .com or .co.ke")
    for suffix in _RESERVED_SUFFIXES:
        if domain == suffix or domain.endswith("." + suffix):
            raise ValueError(f"Domains under .{suffix} can't be used as a custom domain")
    if domain in {h.lower() for h in reserved_hosts if h}:
        raise ValueError("That is this platform's own address and can't be used as a custom domain")
    return domain


def hosts_from_urls(urls: list[str] | tuple[str, ...]) -> list[str]:
    """Hostnames of the platform's own web addresses (settings.PUBLIC_SITE_BASE_URL / CORS_ORIGINS)."""
    hosts = []
    for url in urls:
        host = urlparse(url if "://" in url else f"https://{url}").hostname
        if host:
            hosts.append(host.lower())
    return hosts
