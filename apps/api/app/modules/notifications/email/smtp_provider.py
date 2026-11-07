"""Real SMTP delivery via Python's stdlib (smtplib + email.mime) - no new
dependency needed for this one, unlike reportlab/qrcode this session.

IMPORTANT - not live-tested, same standing caveat as mpesa.py/
stripe_provider.py: this sandbox's network egress doesn't reach an SMTP
server. The protocol usage below (STARTTLS, AUTH LOGIN via smtplib's
built-in login()) follows the standard SMTP-with-auth pattern any provider
(SES, SendGrid SMTP relay, Gmail, a real mail server) expects, but it has
not been exercised against a real server as part of this build. Treat it
as a correctly-shaped starting point, not verified working code."""
import asyncio
import smtplib
import ssl
from email.mime.text import MIMEText

from app.core.config import get_settings
from app.modules.notifications.email.base import EmailProvider, EmailSendResult

settings = get_settings()


class SMTPEmailProvider(EmailProvider):
    name = "smtp"

    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult:
        message = MIMEText(body_text)
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = to
        # smtplib blocks, so run it in a worker thread: a slow mail server must not freeze every other request.
        await asyncio.to_thread(self._deliver, to, message.as_string())
        return EmailSendResult(provider=self.name, accepted=True)

    @staticmethod
    def _deliver(to: str, raw_message: str) -> None:
        # Port 465 is "implicit TLS" (encrypted from the first byte); every other port starts plain and upgrades
        # with STARTTLS when SMTP_USE_TLS is on (587, the default).
        if settings.SMTP_PORT == 465:
            client_cm = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, context=ssl.create_default_context())
        else:
            client_cm = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        with client_cm as client:
            if settings.SMTP_PORT != 465 and settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.sendmail(settings.SMTP_FROM_EMAIL, [to], raw_message)
