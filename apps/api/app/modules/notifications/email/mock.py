"""Fully working, live-testable provider - used by default in dev/test so
password-reset and order-confirmation email flows can be exercised without
a real SMTP server (same "mock provider that actually works" reasoning as
payments/providers/mock.py, spec §51's "create mock providers" principle
applied to a second external-service category)."""
from app.modules.notifications.email.base import EmailProvider, EmailSendResult


class MockEmailProvider(EmailProvider):
    name = "mock"

    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult:
        return EmailSendResult(provider=self.name, accepted=True)
