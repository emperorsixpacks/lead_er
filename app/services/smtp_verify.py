"""DIY email verification via SMTP handshake (no paid service, no key).

How it works:
  1. Resolve the domain's MX records.
  2. Open an SMTP connection to the MX and issue MAIL FROM / RCPT TO (never send).
  3. 250  -> recipient accepted; then probe a random address to detect catch-all.
  4. 550/551/553 -> invalid (no such user).
  5. anything else / errors -> unknown.

Honest limitations:
  - Gmail / Microsoft 365 / Outlook host a large share of business email and
    deliberately DON'T reveal recipient validity at SMTP time (anti-enumeration),
    so they usually answer 250 and this reports "valid" (low confidence).
  - Outbound port 25 is blocked on many residential ISPs and on some PaaS; if the
    connection is refused, results fall back to "unknown".
  - Catch-all domains can produce false positives.

For those reasons this is a free fallback, not a replacement for a real verifier.
"""
import asyncio
import secrets
import smtplib

import dns.resolver

# MAIL FROM address. Some servers reject obviously-invalid sender domains.
FROM_EMAIL = "verify@example.com"

_PORT = 25

_HARD_FAIL = (550, 551, 553)


def _mx_hosts(domain: str) -> list[str]:
    answers = dns.resolver.resolve(domain, "MX")
    return [
        str(r.exchange).rstrip(".")
        for r in sorted(answers, key=lambda r: r.preference)
    ]


def _rcpt(mx_host: str, to_email: str) -> int:
    with smtplib.SMTP(mx_host, _PORT, timeout=15) as smtp:
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        smtp.mail(FROM_EMAIL)
        code, _msg = smtp.rcpt(to_email)
        return code


async def verify_smtp(email: str) -> dict:
    domain = email.rsplit("@", 1)[-1]
    try:
        mxs = await asyncio.to_thread(_mx_hosts, domain)
    except Exception:
        return {"status": "invalid", "raw": "no-mx", "provider": "smtp"}
    if not mxs:
        return {"status": "invalid", "raw": "no-mx", "provider": "smtp"}

    for mx in mxs[:2]:
        try:
            code = await asyncio.to_thread(_rcpt, mx, email)
        except Exception:
            continue

        if code == 250:
            probe = f"lead_er_{secrets.token_hex(6)}@{domain}"
            try:
                pcode = await asyncio.to_thread(_rcpt, mx, probe)
            except Exception:
                pcode = None
            if pcode == 250:
                return {"status": "risky", "raw": "catch-all", "provider": "smtp"}
            return {"status": "valid", "raw": "ok", "provider": "smtp"}

        if code in _HARD_FAIL:
            return {"status": "invalid", "raw": str(code), "provider": "smtp"}

    return {"status": "risky", "raw": "unknown", "provider": "smtp"}
