"""Which ONLINE payment methods a customer can actually be offered right now.

Pure (takes plain values) so it is unit-testable. A method is only listed when
everything it needs is configured - otherwise the storefront would offer a
button that is guaranteed to fail. The `mock` provider is deliberately never
listed: it is a development tool that needs a hand-signed webhook to complete,
and has no place in a customer-facing checkout.

Card payments (Stripe) are not offered yet: they additionally need Stripe.js in
the browser and the PaymentIntent's client_secret exposed by the API.
"""
from __future__ import annotations


def available_methods(daraja: dict[str, str]) -> list[dict[str, str]]:
    needed = ("consumer_key", "consumer_secret", "shortcode", "passkey", "callback_url", "callback_shared_secret")
    methods: list[dict[str, str]] = []
    if all((daraja.get(k) or "").strip() for k in needed):
        methods.append({"provider": "mpesa", "label": "M-Pesa", "input": "phone"})
    return methods
