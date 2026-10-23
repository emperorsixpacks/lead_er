import httpx

from app.config import settings

ZB_URL = "https://api.zerobounce.net/v2/validate"
MV_URL = "https://api.millionverifier.com/api/v3/"

# ZeroBounce status -> our internal email_status.
_ZB_MAP = {
    "valid": "valid",
    "do_not_mail": "invalid",
    "invalid": "invalid",
    "spamtrap": "invalid",
    "abuse": "invalid",
    "catch-all": "risky",
    "unknown": "risky",
}

# MillionVerifier resultcode -> our internal email_status.
_MV_MAP = {
    "1": "valid",   # ok
    "2": "risky",   # catch_all
    "3": "risky",   # unknown
    "5": "invalid",  # disposable
    "6": "invalid",  # invalid
}


async def verify(email: str, ip: str = "") -> dict:
    """Validate an email. Returns {'status': valid|risky|invalid, 'raw': ...}.

    Prefers ZeroBounce; falls back to MillionVerifier when no ZB key is set.
    """
    if settings.email_verify_mock:
        return _mock(email)
    if settings.zerobounce_api_key:
        return await _zerobounce(email, ip)
    if settings.millionverifier_api_key:
        return await _millionverifier(email)
    return {"status": "risky", "raw": None}


def _mock(email: str) -> dict:
    if "bounce" in email or "invalid" in email:
        return {"status": "invalid", "raw": "mock", "provider": "mock"}
    if email.endswith("@example.com") or "test" in email:
        return {"status": "valid", "raw": "mock", "provider": "mock"}
    return {"status": "risky", "raw": "mock", "provider": "mock"}


async def _zerobounce(email: str, ip: str) -> dict:
    params = {"api_key": settings.zerobounce_api_key, "email": email, "ip_address": ip}
    async with httpx.AsyncClient() as client:
        r = await client.get(ZB_URL, params=params)
        r.raise_for_status()
        data = r.json()
    raw = data.get("status", "unknown")
    return {"status": _ZB_MAP.get(raw, "risky"), "raw": raw, "provider": "zerobounce"}


async def _millionverifier(email: str) -> dict:
    params = {"api": settings.millionverifier_api_key, "email": email}
    async with httpx.AsyncClient() as client:
        r = await client.get(MV_URL, params=params)
        r.raise_for_status()
        data = r.json()
    code = str(data.get("resultcode", "3"))
    return {"status": _MV_MAP.get(code, "risky"), "raw": code, "provider": "millionverifier"}
