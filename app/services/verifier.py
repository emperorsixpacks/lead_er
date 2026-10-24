import httpx

from app.config import settings
from app.services import smtp_verify

MV_URL = "https://api.millionverifier.com/api/v3/"

# MillionVerifier resultcode -> our internal email_status.
_MV_MAP = {
    "1": "valid",    # ok
    "2": "risky",    # catch_all
    "3": "risky",    # unknown
    "5": "invalid",  # disposable
    "6": "invalid",  # invalid
}


async def verify(email: str, ip: str = "") -> dict:
    """Validate an email.

    Returns {'status': valid|risky|invalid, 'raw': ..., 'provider': ...}.

    Priority: mock (testing) -> MillionVerifier (if key set) -> DIY SMTP (free).
    """
    if settings.email_verify_mock:
        return _mock(email)
    if settings.millionverifier_api_key:
        return await _millionverifier(email)
    return await smtp_verify.verify_smtp(email)


async def _millionverifier(email: str) -> dict:
    params = {"api": settings.millionverifier_api_key, "email": email}
    async with httpx.AsyncClient() as client:
        r = await client.get(MV_URL, params=params)
        r.raise_for_status()
        data = r.json()
    code = str(data.get("resultcode", "3"))
    return {"status": _MV_MAP.get(code, "risky"), "raw": code, "provider": "millionverifier"}


def _mock(email: str) -> dict:
    if "bounce" in email or "invalid" in email:
        return {"status": "invalid", "raw": "mock", "provider": "mock"}
    if email.endswith("@example.com") or "test" in email:
        return {"status": "valid", "raw": "mock", "provider": "mock"}
    return {"status": "risky", "raw": "mock", "provider": "mock"}
