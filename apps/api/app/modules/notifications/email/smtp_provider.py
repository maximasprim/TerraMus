"""Real SMTP delivery via Python's stdlib (smtplib + email.mime) - no new
dependency needed for this one, unlike reportlab/qrcode this session.

IMPORTANT - not live-tested, same standing caveat as mpesa.py/
stripe_provider.py: this sandbox's network egress doesn't reach an SMTP
server. The protocol usage below (STARTTLS, AUTH LOGIN via smtplib's
built-in login()) follows the standard SMTP-with-auth pattern any provider
(SES, SendGrid SMTP relay, Gmail, a real mail server) expects, but it has
not been exercised against a real server as part of this build. Treat it
as a correctly-shaped starting point, not verified working code."""
import smtplib
from email.mime.text import MIMEText

from app.core.config import get_settings
from app.modules.notifications.email.base import EmailProvider, EmailSendResult

settings = get_settings()


class SMTPEmailProvider(EmailProvider):
    name = "smtp"

    async def send(self, to: str, subject: str, body_text: str) -> EmailSendResult:
        # smtplib is synchronous - this runs it directly rather than wrapping
        # in a thread pool executor. Acceptable here because email sends are
        # already fire-and-forget from a background event handler (same
        # "own session, own task" pattern as notifications/handlers.py), not
        # on the hot path of a request a user is waiting on.
        message = MIMEText(body_text)
        message["Subject"] = subject
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = to

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as client:
            if settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.sendmail(settings.SMTP_FROM_EMAIL, [to], message.as_string())

        return EmailSendResult(provider=self.name, accepted=True)
