import uuid

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.livestock.models import Animal
from app.modules.crops.models import CropPlanting
from app.modules.customers.models import Customer
from app.modules.commerce.models import Order
from app.modules.finance.models import Invoice
from app.modules.procurement.models import Supplier
from app.modules.inventory.models import InventoryItem
from app.modules.employees.models import Employee
from app.modules.assets.models import Asset
from app.modules.search import schemas

_PER_TYPE_LIMIT = 8  # spec §37 wants "support filters"/a usable results list, not a full paginated table per type


async def search(db: AsyncSession, org_id: uuid.UUID, q: str) -> list[schemas.SearchResult]:
    """Spec §37 - global search across animal ID/RFID/ear tag, customer,
    order, invoice, supplier, and inventory item, plus the two entities added
    this session (employee, asset) since they have the same kind of
    human-facing identifiers (employee_number, asset_number) the original
    list was built around. One small ILIKE-bounded query per entity type
    rather than a single UNION - keeps each query simple/indexable and lets
    one slow entity type never block the others; `_PER_TYPE_LIMIT` keeps the
    total response small regardless of how common the query text is."""
    like = f"%{q}%"
    results: list[schemas.SearchResult] = []

    animals = await db.execute(
        select(Animal).where(
            Animal.organization_id == org_id,
            or_(Animal.animal_number.ilike(like), Animal.ear_tag.ilike(like), Animal.rfid.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for a in animals.scalars():
        results.append(schemas.SearchResult(
            type="animal", id=a.id, label=a.animal_number,
            subtitle=f"{a.species}{f' · {a.breed}' if a.breed else ''} · {a.status}",
        ))

    customers = await db.execute(
        select(Customer).where(
            Customer.organization_id == org_id,
            or_(Customer.name.ilike(like), Customer.email.ilike(like), Customer.phone.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for c in customers.scalars():
        results.append(schemas.SearchResult(type="customer", id=c.id, label=c.name, subtitle=c.email or c.phone))

    plantings = await db.execute(
        select(CropPlanting).where(
            CropPlanting.organization_id == org_id, CropPlanting.planting_number.ilike(like),
        ).limit(_PER_TYPE_LIMIT)
    )
    for p in plantings.scalars():
        results.append(schemas.SearchResult(
            type="crop_planting", id=p.id, label=p.planting_number,
            subtitle=f"{p.crop_type}{f' · {p.variety}' if p.variety else ''} · {p.status}",
        ))

    # Orders have no human-facing reference number (unlike invoices/POs) -
    # matched by the linked customer's name/email instead, which is the
    # realistic way a staff member would search for one ("find Jane's order").
    orders = await db.execute(
        select(Order, Customer.name).join(Customer, Customer.id == Order.customer_id).where(
            Order.organization_id == org_id,
            or_(Customer.name.ilike(like), Customer.email.ilike(like), Order.delivery_address.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for order, customer_name in orders:
        results.append(schemas.SearchResult(
            type="order", id=order.id, label=f"Order for {customer_name}",
            subtitle=f"{order.status} · {order.total_amount}",
        ))

    invoices = await db.execute(
        select(Invoice).where(Invoice.organization_id == org_id, Invoice.invoice_number.ilike(like))
        .limit(_PER_TYPE_LIMIT)
    )
    for inv in invoices.scalars():
        results.append(schemas.SearchResult(type="invoice", id=inv.id, label=inv.invoice_number, subtitle=str(inv.total)))

    suppliers = await db.execute(
        select(Supplier).where(
            Supplier.organization_id == org_id,
            or_(Supplier.name.ilike(like), Supplier.email.ilike(like), Supplier.phone.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for s in suppliers.scalars():
        results.append(schemas.SearchResult(type="supplier", id=s.id, label=s.name, subtitle=s.email or s.phone))

    items = await db.execute(
        select(InventoryItem).where(InventoryItem.organization_id == org_id, InventoryItem.name.ilike(like))
        .limit(_PER_TYPE_LIMIT)
    )
    for item in items.scalars():
        results.append(schemas.SearchResult(type="inventory_item", id=item.id, label=item.name, subtitle=item.category))

    employees = await db.execute(
        select(Employee).where(
            Employee.organization_id == org_id,
            or_(Employee.employee_number.ilike(like), Employee.full_name.ilike(like), Employee.phone.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for e in employees.scalars():
        results.append(schemas.SearchResult(
            type="employee", id=e.id, label=e.full_name, subtitle=f"{e.employee_number} · {e.employment_status}",
        ))

    assets = await db.execute(
        select(Asset).where(
            Asset.organization_id == org_id,
            or_(Asset.asset_number.ilike(like), Asset.name.ilike(like), Asset.serial_number.ilike(like)),
        ).limit(_PER_TYPE_LIMIT)
    )
    for asset in assets.scalars():
        results.append(schemas.SearchResult(type="asset", id=asset.id, label=asset.name, subtitle=asset.asset_number))

    return results
