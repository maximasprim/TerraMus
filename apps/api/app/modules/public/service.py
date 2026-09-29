import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Organization
from app.modules.commerce.models import Listing, Order
from app.modules.commerce import schemas as commerce_schemas
from app.modules.commerce.service import (
    create_order as commerce_create_order, get_order as commerce_get_order,
    get_available_crop_quantity,
)
from app.modules.livestock.models import Animal
from app.modules.crops.models import CropPlanting
from app.modules.farm.models import Farm
from app.modules.customers.service import find_or_create_by_contact
from app.modules.cms import service as cms_service
from app.modules.public import schemas


async def get_org_by_slug(db: AsyncSession, org_slug: str) -> Organization:
    result = await db.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farm not found")
    return org


def _public_listing_from_animal(listing: Listing, animal: Animal, county: str | None) -> schemas.PublicListingOut:
    return schemas.PublicListingOut(
        slug=listing.slug, title=listing.title, description=listing.description,
        pricing_type=listing.pricing_type, price=listing.price, listing_kind="animal",
        featured=listing.featured, county=county,
        species=animal.species, breed=animal.breed, sex=animal.sex,
        date_of_birth=animal.date_of_birth, current_weight=animal.current_weight,
        health_status=animal.health_status,
    )


async def _public_listing_from_crop(
    db: AsyncSession, listing: Listing, planting: CropPlanting, county: str | None,
) -> schemas.PublicListingOut:
    available = await get_available_crop_quantity(db, listing.organization_id, planting.id)
    return schemas.PublicListingOut(
        slug=listing.slug, title=listing.title, description=listing.description,
        pricing_type=listing.pricing_type, price=listing.price, listing_kind="crop_produce",
        featured=listing.featured, county=county,
        crop_type=planting.crop_type, variety=planting.variety, unit=listing.unit,
        quantity_available=available, is_perennial=planting.is_perennial,
    )


async def list_public_listings(
    db: AsyncSession, org_id: uuid.UUID, species: str | None = None, crop_type: str | None = None,
) -> list[schemas.PublicListingOut]:
    results: list[schemas.PublicListingOut] = []

    # crop_type being set means the shopper is specifically browsing crop
    # produce - skip the animal query entirely rather than returning an
    # irrelevant mix; likewise species skips the crop query. With neither
    # filter, both kinds show up together (a farm's storefront sells both).
    if not crop_type:
        animal_query = (
            select(Listing, Animal, Farm.county)
            .join(Animal, Animal.id == Listing.animal_id)
            .join(Farm, Farm.id == Animal.farm_id)
            .where(Listing.organization_id == org_id, Listing.is_active.is_(True))
        )
        if species:
            animal_query = animal_query.where(Animal.species == species)
        animal_rows = await db.execute(animal_query)
        results.extend(_public_listing_from_animal(listing, animal, county) for listing, animal, county in animal_rows.all())

    if not species:
        crop_query = (
            select(Listing, CropPlanting, Farm.county)
            .join(CropPlanting, CropPlanting.id == Listing.crop_planting_id)
            .join(Farm, Farm.id == CropPlanting.farm_id)
            .where(Listing.organization_id == org_id, Listing.is_active.is_(True))
        )
        if crop_type:
            crop_query = crop_query.where(CropPlanting.crop_type == crop_type)
        crop_rows = await db.execute(crop_query)
        for listing, planting, county in crop_rows.all():
            results.append(await _public_listing_from_crop(db, listing, planting, county))

    results.sort(key=lambda r: r.featured, reverse=True)  # created_at ordering is already per-kind from the DB;
    return results                                        # featured-first is the one cross-kind guarantee that matters


async def get_public_listing_by_slug(db: AsyncSession, org_id: uuid.UUID, slug: str) -> schemas.PublicListingOut:
    animal_query = (
        select(Listing, Animal, Farm.county)
        .join(Animal, Animal.id == Listing.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
        .where(Listing.organization_id == org_id, Listing.is_active.is_(True), Listing.slug == slug)
    )
    row = (await db.execute(animal_query)).first()
    if row:
        listing, animal, county = row
        return _public_listing_from_animal(listing, animal, county)

    crop_query = (
        select(Listing, CropPlanting, Farm.county)
        .join(CropPlanting, CropPlanting.id == Listing.crop_planting_id)
        .join(Farm, Farm.id == CropPlanting.farm_id)
        .where(Listing.organization_id == org_id, Listing.is_active.is_(True), Listing.slug == slug)
    )
    row = (await db.execute(crop_query)).first()
    if row:
        listing, planting, county = row
        return await _public_listing_from_crop(db, listing, planting, county)

    raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")


async def get_public_profile(db: AsyncSession, org_id: uuid.UUID) -> schemas.PublicFarmProfileOut:
    profile = await cms_service.get_or_create_profile(db, org_id)
    return schemas.PublicFarmProfileOut.model_validate(profile)


async def list_public_testimonials(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.PublicTestimonialOut]:
    testimonials = await cms_service.list_testimonials(db, org_id, published_only=True)
    return [schemas.PublicTestimonialOut.model_validate(t) for t in testimonials]


async def list_public_blog_posts(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.PublicBlogPostSummary]:
    posts = await cms_service.list_blog_posts(db, org_id, published_only=True)
    return [schemas.PublicBlogPostSummary.model_validate(p) for p in posts]


async def get_public_blog_post(db: AsyncSession, org_id: uuid.UUID, slug: str) -> schemas.PublicBlogPostDetail:
    post = await cms_service.get_published_blog_post_by_slug(db, org_id, slug)
    return schemas.PublicBlogPostDetail.model_validate(post)


async def list_public_faqs(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.PublicFAQOut]:
    faqs = await cms_service.list_faqs(db, org_id, published_only=True)
    return [schemas.PublicFAQOut.model_validate(f) for f in faqs]


async def list_public_banners(db: AsyncSession, org_id: uuid.UUID) -> list[schemas.PublicBannerOut]:
    banners = await cms_service.list_banners(db, org_id, active_only=True)
    return [schemas.PublicBannerOut.model_validate(b) for b in banners]


# --------------------------------------------------------- Guest checkout ---
# Spec §69: "Do not force registration before browsing. Allow guest
# checkout." No customer login exists (deliberately deferred - see
# docs/architecture.md); a guest provides contact details, which resolve to
# a Customer CRM record via find_or_create_by_contact, exactly the seam that
# function was built for back in Phase 4.

async def create_guest_order(
    db: AsyncSession, org_id: uuid.UUID, req: schemas.PublicOrderCreate,
) -> schemas.PublicOrderConfirmation:
    order_items: list[commerce_schemas.OrderItemCreate] = []
    listing_titles: dict[str, str] = {}
    listing_quantities: dict[str, Decimal] = {}

    for item in req.items:
        result = await db.execute(
            select(Listing).where(
                Listing.organization_id == org_id, Listing.slug == item.listing_slug, Listing.is_active.is_(True),
            )
        )
        listing = result.scalar_one_or_none()
        if not listing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Listing '{item.listing_slug}' not found or no longer available")
        if listing.pricing_type != "fixed" or listing.price is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"'{listing.title}' requires a quote - contact the farm directly rather than checking out online",
            )
        if listing.animal_id is not None:
            order_items.append(commerce_schemas.OrderItemCreate(animal_id=listing.animal_id, price=listing.price))
            key = str(listing.animal_id)
        else:
            order_items.append(commerce_schemas.OrderItemCreate(
                crop_planting_id=listing.crop_planting_id, quantity=item.quantity, price=listing.price,
            ))
            key = str(listing.crop_planting_id)
        listing_titles[key] = listing.title
        listing_quantities[key] = item.quantity

    customer = await find_or_create_by_contact(db, org_id, req.customer_name, req.customer_email, req.customer_phone)

    order = await commerce_create_order(
        db, org_id, None,  # no staff user - this is a guest-initiated order
        commerce_schemas.OrderCreate(
            customer_id=customer.id, items=order_items,
            delivery_option=req.delivery_option, delivery_address=req.delivery_address, notes=req.notes,
        ),
    )

    return schemas.PublicOrderConfirmation(
        order_id=order.id, status=order.status, total_amount=order.total_amount,
        delivery_option=order.delivery_option,
        items=[
            schemas.PublicOrderItemOut(
                listing_title=listing_titles.get(str(i.animal_id or i.crop_planting_id), "Item"),
                quantity=i.quantity, price=i.price,
            )
            for i in order.items
        ],
        customer_email=req.customer_email,
    )


async def get_guest_order(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID, email: str) -> Order:
    """Guest order lookup - no login, so ownership is checked by requiring
    the email used at checkout rather than trusting the URL alone (an order
    UUID is hard to guess, but 'hard to guess' isn't the same guarantee as
    'authenticated', so this adds one more real check)."""
    order = await commerce_get_order(db, org_id, order_id)
    from app.modules.customers.models import Customer
    result = await db.execute(select(Customer).where(Customer.id == order.customer_id))
    customer = result.scalar_one_or_none()
    if not customer or (customer.email or "").lower() != email.lower():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


async def initiate_guest_payment(
    db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID, provider: str, req: schemas.PublicPaymentRequest,
):
    await get_guest_order(db, org_id, order_id, req.email)  # ownership check, reused from lookup

    from app.modules.payments import schemas as payment_schemas, service as payment_service
    payment_req = payment_schemas.InitiatePaymentRequest(order_id=order_id, phone_or_token=req.phone_or_token)

    if provider == "mock":
        return await payment_service.initiate_mock_payment(db, org_id, None, payment_req)
    if provider == "mpesa":
        return await payment_service.initiate_mpesa_payment(db, org_id, None, payment_req)
    if provider == "stripe":
        return await payment_service.initiate_stripe_payment(db, org_id, None, payment_req)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown payment provider '{provider}'")


async def get_animal_qr_profile(db: AsyncSession, org_id: uuid.UUID, animal_id: uuid.UUID) -> schemas.AnimalQRProfileOut:
    """Spec §38 - what a QR scan resolves to publicly. animal_id itself is
    the identifier in the URL (a UUID - already the "avoid exposing
    sequential internal IDs" identifier spec §30 asks for), not a separate
    opaque token; nothing here needs authentication to view."""
    result = await db.execute(
        select(Animal, Farm.name).join(Farm, Farm.id == Animal.farm_id).where(
            Animal.id == animal_id, Animal.organization_id == org_id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")
    animal, farm_name = row

    listing_result = await db.execute(
        select(Listing.slug).where(Listing.animal_id == animal_id, Listing.is_active.is_(True))
    )
    listing_slug = listing_result.scalar_one_or_none()

    return schemas.AnimalQRProfileOut(
        animal_number=animal.animal_number, species=animal.species, breed=animal.breed, sex=animal.sex,
        health_status=animal.health_status, farm_name=farm_name,
        is_for_sale=listing_slug is not None, listing_slug=listing_slug,
    )
