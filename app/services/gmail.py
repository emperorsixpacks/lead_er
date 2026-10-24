import base64
import smtplib
from email.mime.text import MIMEText

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _gmail_api_send(to: str, subject: str, html: str, sender: str, bcc: str | None):
    """Send via the Gmail API (HTTPS, works on Render)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())

    msg = MIMEText(html, "html")
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject
    if bcc:
        msg["Bcc"] = bcc
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    service = build("gmail", "v1", credentials=creds)
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id"), sent.get("threadId", "")


def _smtp_send(to: str, subject: str, html: str, sender: str, bcc: str | None):
    """Send via Gmail SMTP (app password). Blocked on some PaaS (e.g. Render)."""
    if not settings.gmail_smtp_password:
        raise RuntimeError("Set GMAIL_SMTP_PASSWORD in .env")
    msg = MIMEText(html, "html")
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = subject
    recipients = [to] + ([bcc] if bcc else [])
    with smtplib.SMTP_SSL(settings.gmail_smtp_host, settings.gmail_smtp_port) as server:
        server.login(sender, settings.gmail_smtp_password)
        server.sendmail(sender, recipients, msg.as_string())
    return None, None


def send_email(
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
    bcc: str | None = None,
) -> tuple[str | None, str | None]:
    """Send an email from Gmail.

    Uses the Gmail API (OAuth refresh token) when configured, else SMTP.
    Returns (message_id, thread_id).
    """
    sender = from_email or settings.gmail_smtp_user
    if not sender:
        raise RuntimeError("Set GMAIL_SMTP_USER (your Gmail address) in .env")

    if settings.gmail_refresh_token:
        return _gmail_api_send(to, subject, html, sender, bcc)
    return _smtp_send(to, subject, html, sender, bcc)
