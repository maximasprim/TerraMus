"""One definition of 'the same email address'.

`EmailStr` only lower-cases the DOMAIN part, so `Jane@Farm.com` and `jane@farm.com` were two different
accounts and a phone keyboard that capitalises the first letter made sign-in fail. Every email used to
identify a person is normalised here (trimmed, lower-cased) before it is stored or looked up."""
from typing import Annotated

from pydantic import AfterValidator, EmailStr


def normalize_email(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]
