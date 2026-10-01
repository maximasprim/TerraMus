import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PublicListingImageOut(BaseModel):
    """A photo reference; list order = display order, cover first. When the
    photo lives in a storage bucket, `url`/`thumb_url` are direct CDN links;
    otherwise they're null and the frontend builds the URL from the id
    (/api/v1/media/listing-images/{id}[/thumb])."""
    id: uuid.UUID
    url: str | None = None
    thumb_url: str | None = None


class PublicListingOut(BaseModel):
    """Deliberately narrow - the allowlist principle from spec §38 ('never
    expose sensitive internal information publicly') applies here just as
    much as to QR codes. Excludes acquisition_cost, current_value,
    supplier/previous_owner, internal notes, and exact paddock/location.

    Covers both product kinds a listing can sell (see commerce/models.py's
    Listing docstring): exactly one of the animal-only fields
    (species/breed/sex/date_of_birth/current_weight) or the crop-only fields
    (crop_type/variety/unit/quantity_available) is populated, mirroring
    which one of animal_id/crop_planting_id is set on the underlying row.
    `listing_kind` tells the frontend which set to render without it having
    to guess from which fields happen to be null."""
    model_config = ConfigDict(from_attributes=True)
    slug: str
    title: str
    description: str | None
    pricing_type: str
    price: Decimal | None
    listing_kind: str  # "animal" | "crop_produce"
    featured: bool
    county: str | None
    # animal-only (listing_kind == "animal")
    species: str | None = None
    breed: str | None = None
    sex: str | None = None
    date_of_birth: date | None = None
    current_weight: Decimal | None = None
    health_status: str | None = None  # coarse status only (e.g. "healthy") - no medical detail
    # crop-only (listing_kind == "crop_produce")
    crop_type: str | None = None
    variety: str | None = None
    unit: str | None = None
    quantity_available: Decimal | None = None
    is_perennial: bool | None = None
    # photos, cover first (empty when the farm hasn't uploaded any)
    images: list[PublicListingImageOut] = []


class AnimalQRProfileOut(BaseModel):
    """Spec §38: 'Public QR view could show limited information such as:
    animal ID, species, breed, basic health certification, farm,
    availability. Never expose sensitive internal information publicly.'
    Deliberately excludes acquisition_cost, current_value, supplier,
    previous_owner, exact location, and internal notes - the exact same
    allowlist reasoning PublicListingOut above already applies, extended to
    animals that aren't necessarily listed for sale (a QR tag exists on
    every animal, spec §38, not only ones with an active Listing)."""
    model_config = ConfigDict(from_attributes=True)
    animal_number: str
    species: str
    breed: str | None
    sex: str
    health_status: str  # coarse status only - no medical detail, same as PublicListingOut
    farm_name: str
    is_for_sale: bool
    listing_slug: str | None  # set only when is_for_sale - lets a scanner jump straight to the listing page


class PublicFarmProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    farm_name: str
    tagline: str | None
    farm_story: str | None
    logo_url: str | None
    address: str | None
    county: str | None
    phone: str | None
    email: str | None
    website: str | None
    established_year: int | None


class PublicTestimonialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    customer_name: str
    quote: str
    rating: int | None


class PublicBlogPostSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    title: str
    excerpt: str | None
    cover_image_url: str | None
    author_name: str | None
    published_at: datetime | None


class PublicBlogPostDetail(PublicBlogPostSummary):
    body: str
    seo_title: str | None
    seo_description: str | None


class PublicFAQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    question: str
    answer: str
    category: str | None


class PublicOrderItemRequest(BaseModel):
    listing_slug: str
    quantity: Decimal = Field(default=Decimal("1"), gt=0)  # meaningful for a crop-produce listing; ignored for an animal one


class PublicOrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: EmailStr
    customer_phone: str | None = None
    items: list[PublicOrderItemRequest] = Field(min_length=1)
    delivery_option: str = Field(default="pickup", pattern="^(pickup|delivery)$")
    delivery_address: str | None = None
    notes: str | None = None


class PublicOrderItemOut(BaseModel):
    listing_title: str
    quantity: Decimal
    price: Decimal


class PublicOrderConfirmation(BaseModel):
    order_id: uuid.UUID
    status: str
    total_amount: Decimal
    delivery_option: str
    items: list[PublicOrderItemOut]
    customer_email: str


class PublicPaymentRequest(BaseModel):
    phone_or_token: str
    email: EmailStr  # lightweight ownership check - must match the order's customer


class PublicBannerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    image_url: str
    link_url: str | None


class ResolveDomainOut(BaseModel):
    slug: str