"""Custom domains: validation, non-blocking claims, DNS-proof ownership, Vercel ordering."""
import dns.resolver
import pytest

from app.core import vercel_client

pytestmark = pytest.mark.asyncio


async def _org(client, name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": name, "full_name": "Owner", "email": email, "password": "supersecret123",
    })
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _claim(client, headers, domain: str):
    return await client.post("/api/v1/organization/domain", json={"domain": domain}, headers=headers)


async def _token_for(client, headers) -> str:
    return (await client.get("/api/v1/organization/domain", headers=headers)).json()["dns_instructions"]["txt_record_value"]


@pytest.fixture
def dns_records(monkeypatch):
    """Fake DNS: {hostname: [txt values]} - what the 'real world' has published."""
    published: dict[str, list[str]] = {}

    def fake_resolve(name, rtype):
        if name not in published:
            raise dns.resolver.NXDOMAIN()
        return [f'"{value}"' for value in published[name]]  # dnspython renders TXT rdata with surrounding quotes

    monkeypatch.setattr(dns.resolver, "resolve", fake_resolve)
    return published


@pytest.fixture
def vercel_calls(monkeypatch):
    calls = {"add": [], "remove": []}

    async def add(domain):
        calls["add"].append(domain)
        return {}

    async def remove(domain):
        calls["remove"].append(domain)

    monkeypatch.setattr(vercel_client, "add_domain_to_project", add)
    monkeypatch.setattr(vercel_client, "remove_domain_from_project", remove)
    return calls


@pytest.mark.parametrize("bad", ["https://farm.com", "farm.com/path", "localhost", "*.farm.com", "10.0.0.1", "x.vercel.app", "farm", "a b.com"])
async def test_malformed_domains_are_rejected_with_a_readable_message(client, bad):
    headers = await _org(client, "Dom Farm Bad", f"dombad-{abs(hash(bad))}@example.com")
    resp = await _claim(client, headers, bad)
    assert resp.status_code == 422


async def test_domain_is_normalised_before_it_is_stored(client):
    headers = await _org(client, "Dom Farm Norm", "domnorm@example.com")
    resp = await _claim(client, headers, "  Farm.Example.COM  ")
    assert resp.status_code == 200 and resp.json()["domain"] == "farm.example.com"


async def test_claiming_a_domain_does_not_block_anyone_else(client):
    """Used to be first-come-first-served with no proof: a squatter could lock out the real owner."""
    squatter = await _org(client, "Dom Squatter", "squatter@example.com")
    owner = await _org(client, "Dom Real Owner", "realowner@example.com")
    assert (await _claim(client, squatter, "bigfarm.example.com")).status_code == 200
    assert (await _claim(client, owner, "bigfarm.example.com")).status_code == 200  # was 409


async def test_vercel_is_untouched_until_dns_ownership_is_proven(client, dns_records, vercel_calls):
    headers = await _org(client, "Dom Vercel Order", "domvercel@example.com")
    claimed = await _claim(client, headers, "ordered.example.com")
    assert claimed.json()["vercel_status"] == "pending_dns_verification"
    assert vercel_calls["add"] == []                      # nothing registered just because it was typed in

    failed = await client.post("/api/v1/organization/domain/verify", headers=headers)  # TXT not published yet
    assert failed.json()["verified"] is False and vercel_calls["add"] == []

    dns_records["_farmplatform-verify.ordered.example.com"] = [await _token_for(client, headers)]
    ok = await client.post("/api/v1/organization/domain/verify", headers=headers)
    assert ok.json()["verified"] is True and ok.json()["vercel_status"] == "added"
    assert vercel_calls["add"] == ["ordered.example.com"]


async def test_only_the_org_that_publishes_its_own_token_gets_verified(client, dns_records, vercel_calls):
    squatter = await _org(client, "Dom Squat 2", "squat2@example.com")
    owner = await _org(client, "Dom Owner 2", "owner2@example.com")
    await _claim(client, squatter, "contested.example.com")
    await _claim(client, owner, "contested.example.com")

    # the real owner controls DNS, so only THEIR token is published
    dns_records["_farmplatform-verify.contested.example.com"] = [await _token_for(client, owner)]
    assert (await client.post("/api/v1/organization/domain/verify", headers=squatter)).json()["verified"] is False
    assert (await client.post("/api/v1/organization/domain/verify", headers=owner)).json()["verified"] is True

    resolved = await client.get("/api/v1/public/resolve-domain", params={"host": "contested.example.com"})
    assert resolved.status_code == 200
    assert (await client.get("/api/v1/organization/domain", headers=squatter)).json()["verified"] is False


async def test_proving_dns_control_releases_a_stale_verified_holder(client, dns_records, vercel_calls):
    """E.g. the old owner let the domain lapse and the new owner bought it."""
    old = await _org(client, "Dom Old Holder", "oldholder@example.com")
    new = await _org(client, "Dom New Holder", "newholder@example.com")
    await _claim(client, old, "handover.example.com")
    dns_records["_farmplatform-verify.handover.example.com"] = [await _token_for(client, old)]
    assert (await client.post("/api/v1/organization/domain/verify", headers=old)).json()["verified"] is True

    await _claim(client, new, "handover.example.com")
    dns_records["_farmplatform-verify.handover.example.com"] = [await _token_for(client, new)]  # DNS now proves the NEW owner
    assert (await client.post("/api/v1/organization/domain/verify", headers=new)).json()["verified"] is True

    released = (await client.get("/api/v1/organization/domain", headers=old)).json()
    assert released["domain"] is None and released["verified"] is False


async def test_an_unverified_claimant_cannot_remove_a_verified_domain_from_vercel(client, dns_records, vercel_calls):
    squatter = await _org(client, "Dom Squat 3", "squat3@example.com")
    owner = await _org(client, "Dom Owner 3", "owner3@example.com")
    await _claim(client, squatter, "live.example.com")
    await _claim(client, owner, "live.example.com")
    dns_records["_farmplatform-verify.live.example.com"] = [await _token_for(client, owner)]
    await client.post("/api/v1/organization/domain/verify", headers=owner)

    assert (await client.delete("/api/v1/organization/domain", headers=squatter)).status_code in (200, 204)
    assert vercel_calls["remove"] == []                    # the owner's live domain was NOT touched

    assert (await client.delete("/api/v1/organization/domain", headers=owner)).status_code in (200, 204)
    assert vercel_calls["remove"] == ["live.example.com"]  # the verified owner removing it does unregister it


async def test_resubmitting_a_verified_domain_does_not_reset_it(client, dns_records, vercel_calls):
    headers = await _org(client, "Dom Resubmit", "domresubmit@example.com")
    await _claim(client, headers, "stable.example.com")
    dns_records["_farmplatform-verify.stable.example.com"] = [await _token_for(client, headers)]
    await client.post("/api/v1/organization/domain/verify", headers=headers)

    again = await _claim(client, headers, "Stable.Example.com")
    assert again.status_code == 200 and again.json()["verified"] is True   # storefront stays online


async def test_switching_domains_unregisters_the_old_verified_one(client, dns_records, vercel_calls):
    headers = await _org(client, "Dom Switch", "domswitch@example.com")
    await _claim(client, headers, "first.example.com")
    dns_records["_farmplatform-verify.first.example.com"] = [await _token_for(client, headers)]
    await client.post("/api/v1/organization/domain/verify", headers=headers)

    await _claim(client, headers, "second.example.com")
    assert vercel_calls["remove"] == ["first.example.com"]
    assert (await client.get("/api/v1/organization/domain", headers=headers)).json()["verified"] is False
