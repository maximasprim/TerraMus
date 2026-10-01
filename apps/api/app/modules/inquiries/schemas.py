import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class InquiryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    message: str = Field(min_length=5, max_length=2000)
    listing_slug: str | None = Field(default=None, max_length=255)
    # Honeypot: real visitors never see or fill this field; naive bots fill
    # every input. A non-empty value is silently discarded (see service).
    website: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _needs_a_way_to_reply(self):
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("Please provide an email address or phone number so the farm can reply")
        return self


class InquiryReceipt(BaseModel):
    received: bool = True


class InquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    message: str
    listing_slug: str | None
    status: str
    created_at: datetime


class InquiryStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|read|replied|archived)$")


class InquirySummary(BaseModel):
    new: int = 0
    read: int = 0
    replied: int = 0
    archived: int = 0
