"""Pure unit tests for custom-domain validation (no database)."""
import pytest

from app.core.domain_validation import hosts_from_urls, normalise_domain


@pytest.mark.parametrize("raw,expected", [
    (" Farm.Example.COM ", "farm.example.com"),
    ("farm.co.ke", "farm.co.ke"),
    ("shop.my-farm.org.", "shop.my-farm.org"),      # trailing dot from a DNS panel
    ("xn--frm-5qa.com", "xn--frm-5qa.com"),         # punycode
    ("123farm.com", "123farm.com"),
])
def test_valid_domains_are_normalised(raw, expected):
    assert normalise_domain(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", "https://farm.com", "http://farm.com/x", "farm.com/path", "farm.com:8080", "*.farm.com",
    "farm", "localhost", "a b.com", "farm..com", "-bad.com", "bad-.com", "10.0.0.1", "192.168.1.1",
    "my_farm.com", "farm.c", "farm.123", "x.vercel.app", "vercel.app", "foo.localhost", "a.internal",
    "user@farm.com", "farm.com?x=1", "farm.com#a", "a" * 64 + ".com", "a." * 130 + "com",
])
def test_invalid_or_reserved_domains_are_rejected(raw):
    with pytest.raises(ValueError):
        normalise_domain(raw)


def test_the_platforms_own_hosts_cannot_be_claimed():
    own = hosts_from_urls(["https://app.terramus.co.ke", "admin.terramus.co.ke", "http://localhost:3000"])
    assert own == ["app.terramus.co.ke", "admin.terramus.co.ke", "localhost"]
    with pytest.raises(ValueError):
        normalise_domain("APP.terramus.co.ke", own)
    assert normalise_domain("shop.terramus.co.ke", own) == "shop.terramus.co.ke"
