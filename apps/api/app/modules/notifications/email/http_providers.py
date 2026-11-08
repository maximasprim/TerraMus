"""Email over HTTPS (Brevo, Resend). Many hosts (Render's free tier, for one) block outgoing SMTP ports, but HTTPS always
works. The sender address is SMTP_FROM_EMAIL and must be verified with the service; the key is EMAIL_API_KEY.
A non-2xx answer raises, so a failed send is never mistaken for a delivered one."""
import httpx

from app.core.config import get_settings
from app.modules.notifications.email.base import EmailProvider, EmailSendResult

settings = get_settings()
TIMEOUT = 15.0


def _client() -> httpx.AsyncClient:   # one place to swap in a fake transport in tests
    return httpx.AsyncClient(timeout=TIMEOUT)


def _check(resp: httpx.Response) -> None:
    if resp.status_code >= 300:
        raise RuntimeError(f"email service refused the message ({resp.status_code}): {resp.text[:300]}")


class BrevoEmailProvider(EmailProvider):
    name = "brevo"

    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult:
        async with _client() as c:
            resp = await c.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": settings.EMAIL_API_KEY, "accept": "application/json"},
                json={"sender": {"email": settings.SMTP_FROM_EMAIL, "name": settings.EMAIL_FROM_NAME},
                      "to": [{"email": to}], "subject": subject, "textContent": body_text},
            )
        _check(resp)
        return EmailSendResult(provider=self.name, accepted=True)


class ResendEmailProvider(EmailProvider):
    name = "resend"

    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult:
        async with _client() as c:
            resp = await c.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
                json={"from": f"{settings.EMAIL_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>", "to": [to],
                      "subject": subject, "text": body_text},
            )
        _check(resp)
        return EmailSendResult(provider=self.name, accepted=True)
