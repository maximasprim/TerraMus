from app.modules.payments.providers.base import PaymentProvider
from app.modules.payments.providers.mock import MockProvider
from app.modules.payments.providers.mpesa import MpesaDarajaProvider
from app.modules.payments.providers.stripe_provider import StripeProvider

_PROVIDERS: dict[str, type[PaymentProvider]] = {
    "mock": MockProvider,
    "mpesa": MpesaDarajaProvider,
    "stripe": StripeProvider,
}


def get_provider(name: str) -> PaymentProvider:
    provider_class = _PROVIDERS.get(name)
    if not provider_class:
        raise ValueError(f"Unknown payment provider '{name}'")
    return provider_class()
