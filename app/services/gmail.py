import smtplib
from email.mime.text import MIMEText

from app.config import settings


def send_email(
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
    bcc: str | None = None,
) -> tuple[None, None]:
    """Send via Gmail SMTP using an app password. Returns (None, None).

    Gmail requires 2-Step Verification + an App Password (16 chars), not your
    account password. See: https://myaccount.google.com/apppasswords
    """
    sender = from_email or settings.gmail_smtp_user
    if not sender or not settings.gmail_smtp_password:
        raise RuntimeError("Set GMAIL_SMTP_USER and GMAIL_SMTP_PASSWORD in .env")

    msg = MIMEText(html, "html")
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject

    # Bcc goes in the envelope only (not the headers), so the recipient never
    # sees it and your copy still lands in your inbox.
    recipients = [to] + ([bcc] if bcc else [])

    with smtplib.SMTP_SSL(settings.gmail_smtp_host, settings.gmail_smtp_port) as server:
        server.login(sender, settings.gmail_smtp_password)
        server.sendmail(sender, recipients, msg.as_string())

    # SMTP doesn't expose Gmail's message/thread id; tracking is token-based anyway.
    return None, None
