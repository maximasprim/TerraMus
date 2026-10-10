"""Pure unit tests for M-Pesa phone normalisation and payment-method availability (no database)."""
import pytest

from app.core.phone import INVALID_MESSAGE, normalise_ke_msisdn
from app.modules.payments.availability import available_methods


@pytest.mark.parametrize("raw,expected", [
    ("0712345678", "254712345678"),
    ("0712 345 678", "254712345678"),
    ("+254 712-345-678", "254712345678"),
    ("254712345678", "254712345678"),
    ("712345678", "254712345678"),
    ("0112345678", "254112345678"),            # Safaricom's newer 01xx range
    ("(0722) 111.222", "254722111222"),
])
def test_common_ways_of_typing_a_kenyan_number_are_normalised(raw, expected):
    assert normalise_ke_msisdn(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "071234567", "07123456789", "254812345678", "0812345678", "+1 415 555 0100", "254712345", "0712-345-67x", None])
def test_anything_else_is_rejected_with_a_friendly_message(raw):
    with pytest.raises(ValueError) as exc:
        normalise_ke_msisdn(raw)
    assert str(exc.value) == INVALID_MESSAGE


FULL = dict(consumer_key="k", consumer_secret="s", shortcode="174379", passkey="p", callback_url="https://x/cb", callback_shared_secret="z")


def test_mpesa_is_offered_only_when_fully_configured():
    assert available_methods(FULL) == [{"provider": "mpesa", "label": "M-Pesa", "input": "phone"}]
    assert available_methods({}) == []


@pytest.mark.parametrize("missing", list(FULL))
def test_any_missing_setting_hides_the_method(missing):
    assert available_methods({**FULL, missing: ""}) == []   # never offer a button that is guaranteed to fail
