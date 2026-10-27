"""Role grants for the new permission codes: least privilege, for new orgs AND migrated ones."""
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

EXPECT = {
    "Farm Owner": {"feedlot.read", "feedlot.weigh", "feedlot.manage", "training.read", "training.manage", "groups.read", "groups.record", "groups.manage", "fodder.read", "fodder.record", "fodder.manage"},
    "Farm Manager": {"feedlot.read", "feedlot.weigh", "feedlot.manage", "training.read", "training.manage", "groups.read", "groups.record", "groups.manage", "fodder.read", "fodder.record", "fodder.manage"},
    "Livestock Manager": {"feedlot.read", "feedlot.weigh", "feedlot.manage", "groups.read", "groups.record", "groups.manage", "fodder.read", "fodder.record"},
    "Farm Worker": {"feedlot.read", "feedlot.weigh", "groups.read", "groups.record", "fodder.read", "fodder.record"},
    "Veterinarian": {"feedlot.read", "groups.read", "fodder.read"},
    "Accountant": {"feedlot.read", "training.read", "groups.read", "fodder.read"},
    "Sales Manager": {"feedlot.read", "training.read", "training.manage", "fodder.read"},
}
NEW = {c for s in EXPECT.values() for c in s}


async def _grants(engine, org_name):
    async with engine.connect() as c:
        rows = (await c.execute(text(
            "SELECT r.name, p.code FROM roles r JOIN organizations o ON o.id = r.organization_id "
            "JOIN role_permissions rp ON rp.role_id = r.id JOIN permissions p ON p.id = rp.permission_id "
            "WHERE o.name = :n AND p.code = ANY(:codes)"), {"n": org_name, "codes": list(NEW)})).all()
    out = {}
    for role, code in rows:
        out.setdefault(role, set()).add(code)
    return out


async def test_new_org_roles_get_exactly_the_intended_new_permissions(client, engine):
    await client.post("/api/v1/auth/register", json={"organization_name": "Grant Farm", "full_name": "Owner One", "email": "gr@example.com", "password": "supersecret123"})
    got = await _grants(engine, "Grant Farm")
    for role, expected in EXPECT.items():
        assert got.get(role, set()) == expected, (role, got.get(role), expected)
    assert "feedlot.manage" not in got["Farm Worker"] and "training.manage" not in got["Accountant"]


async def test_migration_grants_existing_orgs_the_same_permissions(client, engine):
    """Re-run the permission-seeding parts of 0029/0031 against an org created BEFORE them (simulated by revoking first)."""
    await client.post("/api/v1/auth/register", json={"organization_name": "Legacy Farm", "full_name": "Owner One", "email": "lg@example.com", "password": "supersecret123"})
    async with engine.begin() as c:   # pretend the org predates the new codes
        await c.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": list(NEW)})
    assert await _grants(engine, "Legacy Farm") == {}
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib.util, pathlib
    vdir = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"

    def load(name):
        spec = importlib.util.spec_from_file_location(name, vdir / f"{name}.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod
    m29, m31, m35 = load("0029_feedlot_core"), load("0031_training_groups_fuel_feedback_photos"), load("0035_fodder_production")
    async with engine.begin() as conn:
        def run(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                m29._seed_permissions(); m31._seed_permissions(); m35._seed_permissions()
        await conn.run_sync(run)
    got = await _grants(engine, "Legacy Farm")
    for role, expected in EXPECT.items():
        assert got.get(role, set()) == expected, (role, got.get(role), expected)
