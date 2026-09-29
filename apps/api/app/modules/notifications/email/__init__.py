from app.modules.notifications.email.base import EmailProvider
from app.modules.notifications.email.mock import MockEmailProvider
from app.modules.notifications.email.smtp_provider import SMTPEmailProvider

_PROVIDERS: dict[str, type[EmailProvider]] = {
    "mock": MockEmailProvider,
    "smtp": SMTPEmailProvider,
}


def get_email_provider(name: str) -> EmailProvider:
    provider_class = _PROVIDERS.get(name)
    if not provider_class:
        raise ValueError(f"Unknown email provider '{name}'")
    return provider_class()
