"""Kenyan mobile-number normalisation for M-Pesa (pure, no app imports).

Daraja's STK Push needs the MSISDN as 254XXXXXXXXX (12 digits, no plus, no
spaces). Customers type 0712 345 678, +254 712 345 678, 712345678... and a
number in any other shape just fails at the provider with an unhelpful error.
"""
from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-().]")

INVALID_MESSAGE = "Enter a valid Kenyan mobile number, like 0712 345 678"


def normalise_ke_msisdn(raw: str) -> str:
    digits = _SEPARATORS.sub("", raw or "")
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        raise ValueError(INVALID_MESSAGE)
    if len(digits) == 12 and digits.startswith("254"):
        pass
    elif len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    else:
        raise ValueError(INVALID_MESSAGE)
    if digits[3] not in "17":  # Kenyan mobile ranges are 07xx and 01xx
        raise ValueError(INVALID_MESSAGE)
    return digits
