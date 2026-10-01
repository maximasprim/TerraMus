import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PRICING_TYPE_PATTERN = "^(fixed|negotiable|price_on_request)$"
ORDER_STATUS_PATTERN = (
    "^(pending|payment_pending|paid|processing|ready_for_fulfillment|"
    "dispatched|delivered|completed|cancelled|refunded|partially_refunded|failed)$"
)


class ListingCreate(BaseModel):
    """Exactly one of animal_id/crop_planting_id must be given - see
    Listing's docstring in models.py."""
    animal_id: uuid.UUID | None = None
    crop_planting_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    pricing_type: str = Field(default="fixed", pattern=PRICING_TYPE_PATTERN)
    price: Decimal | None = None  # per-unit price for a crop-produce listing
    unit: str | None = None  # required (validated in service.py) for a crop-produce listing
    low_stock_threshold: Decimal | None = None  # crop-produce only - ignored for an animal listing
    featured: bool = False

    @model_validator(mode="after")
    def _exactly_one_product(self) -> "ListingCreate":
        if (self.animal_id is None) == (self.crop_planting_id is None):
            raise ValueError("Provide exactly one of animal_id or crop_planting_id")
        return self


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID | None
    crop_planting_id: uuid.UUID | None
    slug: str
    title: str
    description: str | None
    pricing_type: str
    price: Decimal | None
    unit: str | None
    low_stock_threshold: Decimal | None
    featured: bool
    is_active: bool
    created_at: datetime
    # Photo summary for the admin grid. Populated by GET /listings; every
    # other endpoint returning ListingOut just reports the defaults.
    cover_image_id: uuid.UUID | None = None
    cover_thumb_url: str | None = None  # direct bucket URL when photos live in storage (else use the media endpoint)
    image_count: int = 0


class ListingImageOut(BaseModel):
    """Photo metadata only. Bytes are served by /api/v1/media, or - when the
    photo lives in a storage bucket - directly from `url` / `thumb_url`."""
    id: uuid.UUID
    position: int
    width: int
    height: int
    size_bytes: int
    content_type: str
    url: str | None = None
    thumb_url: str | None = None


class ListingImageOrder(BaseModel):
    """The listing's photo ids in their new display order (first = cover)."""
    image_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class ListingUpdate(BaseModel):
    """Spec §71 gap (no edit-listing existed): partial update on title,
    description, price, featured flag. Deliberately does NOT allow changing
    `animal_id` or `pricing_type` here - re-pointing a listing at a
    different animal, or switching pricing model, is enough of a different
    operation (spec §17's fixed/negotiable/price_on_request distinction
    changes what fields are even valid) that it's out of scope for a plain
    edit; deactivate and recreate for that."""
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = None
    featured: bool | None = None


class ListingFilter(BaseModel):
    species: str | None = None
    crop_type: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    featured_only: bool = False


class ReservationCreate(BaseModel):
    animal_id: uuid.UUID
    customer_id: uuid.UUID
    reservation_date: date
    expiry_date: date
    deposit_amount: Decimal | None = None
    notes: str | None = None


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID
    customer_id: uuid.UUID
    reservation_date: date
    expiry_date: date
    deposit_amount: Decimal | None
    status: str
    notes: str | None
    created_at: datetime


class OrderItemCreate(BaseModel):
    """Exactly one of animal_id/crop_planting_id must be given. `quantity`
    is meaningless for an animal item (always exactly one unit - left at its
    default of 1) and meaningful for a crop-produce item (how much is being
    bought, in the listing's unit). `price` is a per-unit price for a
    crop-produce item, a flat price for an animal item."""
    animal_id: uuid.UUID | None = None
    crop_planting_id: uuid.UUID | None = None
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    price: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def _exactly_one_product(self) -> "OrderItemCreate":
        if (self.animal_id is None) == (self.crop_planting_id is None):
            raise ValueError("Provide exactly one of animal_id or crop_planting_id")
        return self


class OrderCreate(BaseModel):
    customer_id: uuid.UUID
    items: list[OrderItemCreate] = Field(min_length=1)
    delivery_option: str = Field(default="pickup", pattern="^(pickup|delivery)$")
    delivery_address: str | None = None
    notes: str | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    animal_id: uuid.UUID | None
    crop_planting_id: uuid.UUID | None
    quantity: Decimal
    price: Decimal


class OrderStatusChange(BaseModel):
    status: str = Field(pattern=ORDER_STATUS_PATTERN)
    reason: str | None = None


class OrderStatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    from_status: str | None
    to_status: str
    reason: str | None
    changed_by: uuid.UUID | None
    changed_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    delivery_option: str
    delivery_address: str | None
    total_amount: Decimal
    notes: str | None
    created_at: datetime
    items: list[OrderItemOut] = []
    status_events: list[OrderStatusEventOut] = []
