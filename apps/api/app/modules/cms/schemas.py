import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class FarmProfileUpdate(BaseModel):
    farm_name: str | None = None
    tagline: str | None = None
    farm_story: str | None = None
    logo_url: str | None = None
    address: str | None = None
    county: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    established_year: int | None = None


class FarmProfileOut(BaseModel):
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


class TestimonialCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    quote: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    is_published: bool = False
    is_featured: bool = False
    sort_order: int = 0


class TestimonialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    customer_name: str
    quote: str
    rating: int | None
    is_published: bool
    is_featured: bool
    sort_order: int


class BlogPostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    excerpt: str | None = None
    body: str = Field(min_length=1)
    cover_image_url: str | None = None
    author_name: str | None = None
    is_published: bool = False
    seo_title: str | None = None
    seo_description: str | None = None


class BlogPostUpdate(BaseModel):
    title: str | None = None
    excerpt: str | None = None
    body: str | None = None
    cover_image_url: str | None = None
    author_name: str | None = None
    is_published: bool | None = None
    seo_title: str | None = None
    seo_description: str | None = None


class BlogPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    title: str
    excerpt: str | None
    body: str
    cover_image_url: str | None
    author_name: str | None
    is_published: bool
    published_at: datetime | None
    seo_title: str | None
    seo_description: str | None
    created_at: datetime


class FAQCreate(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1)
    category: str | None = None
    sort_order: int = 0
    is_published: bool = False


class FAQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question: str
    answer: str
    category: str | None
    sort_order: int
    is_published: bool


class BannerCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    image_url: str = Field(min_length=1, max_length=500)
    link_url: str | None = None
    sort_order: int = 0
    is_active: bool = True
    starts_at: date | None = None
    ends_at: date | None = None


class BannerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    image_url: str
    link_url: str | None
    sort_order: int
    is_active: bool
    starts_at: date | None
    ends_at: date | None
