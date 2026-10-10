import uuid

from pydantic import BaseModel

RESULT_TYPES = (
    "animal", "crop_planting", "customer", "order", "invoice", "supplier", "inventory_item", "employee", "asset",
)


class SearchResult(BaseModel):
    """One unified shape across every searchable entity (spec §37) - a
    result card doesn't need to know which table it came from to render a
    type badge, a label, a subtitle, and a link."""
    type: str
    id: uuid.UUID
    label: str
    subtitle: str | None = None
