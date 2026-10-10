# Single source of truth for provider lookup (including the production gate on
# the mock provider) lives in payments/providers/__init__.py. Re-exported here
# so `from app.modules.payments import get_provider` keeps working.
from app.modules.payments.providers import get_provider  # noqa: F401


# from fastapi import HTTPException

# from app.core.config import get_settings
# from app.core.security_checks import mock_payments_enabled
# from app.modules.payments.providers.base import PaymentProvider
# from app.modules.payments.providers.mock import MockProvider
# from app.modules.payments.providers.mpesa import MpesaDarajaProvider
# from app.modules.payments.providers.stripe_provider import StripeProvider

# _PROVIDERS: dict[str, type[PaymentProvider]] = {
#     "mock": MockProvider,
#     "mpesa": MpesaDarajaProvider,
#     "stripe": StripeProvider,
# }


# def get_provider(name: str) -> PaymentProvider:
#     if name == "mock":
#         # The mock provider "succeeds" with no real payment, and its public
#         # webhook is protected only by a shared secret. Refuse it outright
#         # (404, as if it doesn't exist) wherever it isn't explicitly safe.
#         settings = get_settings()
#         if not mock_payments_enabled(settings.ENV, settings.ALLOW_MOCK_PAYMENTS, settings.MOCK_PAYMENT_SECRET):
#             raise HTTPException(status_code=404, detail="Payment provider not available")
#     provider_class = _PROVIDERS.get(name)
#     if not provider_class:
#         raise ValueError(f"Unknown payment provider '{name}'")
#     return provider_class()
