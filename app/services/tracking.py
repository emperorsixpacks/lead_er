import secrets
from urllib.parse import quote

from app.config import settings

# 1x1 transparent GIF
TRANSPARENT_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def new_token() -> str:
    return secrets.token_urlsafe(12)


def tracking_base() -> str:
    return settings.tracking_base_url.rstrip("/")


def pixel_url(token: str) -> str:
    return f"{tracking_base()}/o/{token}.gif"


def wrap_link(token: str, url: str) -> str:
    return f"{tracking_base()}/c/{token}?u={quote(url, safe='')}"


def unsubscribe_url(token: str) -> str:
    return f"{tracking_base()}/u/{token}"


def pixel_html(token: str) -> str:
    return (
        f'<img src="{pixel_url(token)}" width="1" height="1" '
        'alt="" style="display:block;width:1px;height:1px;border:0;">'
    )
