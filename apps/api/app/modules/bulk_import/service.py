import csv
import io
import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.livestock import schemas as livestock_schemas, service as livestock_service
from app.modules.crops import schemas as crops_schemas, service as crops_service
from app.modules.customers import schemas as customer_schemas, service as customer_service
from app.modules.procurement import schemas as procurement_schemas, service as procurement_service
from app.modules.inventory import schemas as inventory_schemas, service as inventory_service
from app.modules.bulk_import import schemas


def _parse_csv(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig")  # -sig strips a BOM, which Excel-exported CSVs commonly add
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _clean_row(row: dict[str, str], bool_fields: set[str] = frozenset()) -> dict:
    """Blank cells become 'not provided' (dropped entirely, letting the
    Create schema's own required/optional/default rules decide what happens
    next) rather than empty strings, which would otherwise fail validation
    on every optional field a spreadsheet leaves blank. Known boolean
    columns get a light token conversion since raw CSV text like 'true' or
    '1' doesn't validate as a Python bool without it."""
    cleaned = {}
    for key, value in row.items():
        if key is None or value is None:
            continue
        value = value.strip()
        if value == "":
            continue
        if key in bool_fields:
            cleaned[key] = value.lower() in ("true", "1", "yes")
        else:
            cleaned[key] = value
    return cleaned


async def _run_import(
    rows: list[dict[str, str]], bool_fields: set[str],
    schema_cls, create_fn, dry_run: bool,
) -> schemas.BulkImportResult:
    """Spec §73's "Never blindly import invalid records": every row is
    validated independently. A bad row never blocks the good ones (unlike a
    single all-or-nothing transaction), and - critically - a bad row is
    never silently skipped either; it's reported by row number so whoever
    uploaded the file can fix and re-run just that row."""
    errors: list[schemas.RowError] = []
    valid_payloads = []

    for i, raw_row in enumerate(rows, start=2):  # row 1 is the header
        cleaned = _clean_row(raw_row, bool_fields)
        try:
            payload = schema_cls(**cleaned)
        except ValidationError as exc:
            first_error = exc.errors()[0]
            field = ".".join(str(loc) for loc in first_error["loc"])
            errors.append(schemas.RowError(row=i, error=f"{field}: {first_error['msg']}"))
            continue
        valid_payloads.append(payload)

    imported = 0
    if not dry_run:
        for payload in valid_payloads:
            await create_fn(payload)
            imported += 1

    return schemas.BulkImportResult(
        dry_run=dry_run, total_rows=len(rows), valid_rows=len(valid_payloads), imported=imported, errors=errors,
    )


async def import_customers(db: AsyncSession, org_id: uuid.UUID, raw: bytes, dry_run: bool) -> schemas.BulkImportResult:
    rows = _parse_csv(raw)
    return await _run_import(
        rows, bool_fields=set(), schema_cls=customer_schemas.CustomerCreate,
        create_fn=lambda payload: customer_service.create_customer(db, org_id, payload), dry_run=dry_run,
    )


async def import_suppliers(db: AsyncSession, org_id: uuid.UUID, raw: bytes, dry_run: bool) -> schemas.BulkImportResult:
    rows = _parse_csv(raw)
    return await _run_import(
        rows, bool_fields=set(), schema_cls=procurement_schemas.SupplierCreate,
        create_fn=lambda payload: procurement_service.create_supplier(db, org_id, payload), dry_run=dry_run,
    )


async def import_inventory_items(
    db: AsyncSession, org_id: uuid.UUID, raw: bytes, dry_run: bool,
) -> schemas.BulkImportResult:
    rows = _parse_csv(raw)
    return await _run_import(
        rows, bool_fields={"allow_negative_stock"}, schema_cls=inventory_schemas.InventoryItemCreate,
        create_fn=lambda payload: inventory_service.create_item(db, org_id, payload), dry_run=dry_run,
    )


async def import_livestock(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, farm_id: uuid.UUID,
    default_location_id: uuid.UUID | None, raw: bytes, dry_run: bool,
) -> schemas.BulkImportResult:
    """Unlike the other three, AnimalCreate requires `farm_id` - a bulk
    livestock import is inherently "import N animals into this farm", so
    farm_id is a call parameter applied to every row rather than a CSV
    column, the same way a real spreadsheet-import tool asks "which farm?"
    once up front rather than making the user repeat it 200 times.
    `location_id` can still be overridden per row if the CSV includes that
    column; `default_location_id` fills in when it doesn't."""
    rows = _parse_csv(raw)
    for row in rows:
        row["farm_id"] = str(farm_id)
        if not row.get("location_id") and default_location_id:
            row["location_id"] = str(default_location_id)
    return await _run_import(
        rows, bool_fields={"estimated_birth_date"}, schema_cls=livestock_schemas.AnimalCreate,
        create_fn=lambda payload: livestock_service.create_animal(db, org_id, user_id, payload), dry_run=dry_run,
    )


async def import_crops(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, farm_id: uuid.UUID,
    default_location_id: uuid.UUID | None, raw: bytes, dry_run: bool,
) -> schemas.BulkImportResult:
    """Same "farm_id applied to every row, location_id optionally per-row"
    shape as import_livestock above - a bulk crop import is likewise
    "plant N plots into this farm"."""
    rows = _parse_csv(raw)
    for row in rows:
        row["farm_id"] = str(farm_id)
        if not row.get("location_id") and default_location_id:
            row["location_id"] = str(default_location_id)
    return await _run_import(
        rows, bool_fields={"is_perennial"}, schema_cls=crops_schemas.CropPlantingCreate,
        create_fn=lambda payload: crops_service.create_planting(db, org_id, user_id, payload), dry_run=dry_run,
    )
