"""Free website/email discovery: DuckDuckGo search + RDAP (WHOIS) lookup.

Used to replace blind domain-guessing: given a business name + city, find the
real domain via search, then optionally pull the registrant email via RDAP.
"""
import re
import urllib.parse
from urllib.parse import urlparse

import httpx

DDG_URL = "https://html.duckduckgo.com/html/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# Results to skip: directories/social/aggregators, not the business's own site.
_DIRECTORY_DOMAINS = {
    "chamberofcommerce.com", "loc8nearme.com", "yelp.com", "yellowpages.com",
    "mapquest.com", "manta.com", "bizapedia.com", "facebook.com", "linkedin.com",
    "instagram.com", "twitter.com", "x.com", "indeed.com", "glassdoor.com", "bbb.org",
    "dandb.com", "zoominfo.com", "apollo.io", "hunter.io", "nicelocal.com",
    "cybo.com", "us-info.com", "opencorporates.com", "buzzfile.com", "tripadvisor.com",
}


async def search_domains(query: str, limit: int = 5) -> list[str]:
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(DDG_URL, params={"q": query}, timeout=20)
        r.raise_for_status()

    domains: list[str] = []
    for m in re.finditer(r'uddg=([^"&]+)', r.text):
        url = urllib.parse.unquote(m.group(1))
        dom = urlparse(url).netloc.lower().removeprefix("www.")
        if not dom or not dom.count("."):
            continue
        if any(d in dom for d in _DIRECTORY_DOMAINS):
            continue
        if dom not in domains:
            domains.append(dom)
        if len(domains) >= limit:
            break
    return domains


async def resolve_website(name: str, city: str = "", state: str = "") -> str | None:
    query = f'"{name}" {city} {state}'.strip()
    try:
        domains = await search_domains(query)
    except Exception:
        return None
    return domains[0] if domains else None


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# DDG's own anti-bot / junk addresses.
_JUNK = ("duckduckgo.com", "example.com", "sentry.io", "w3.org", "gmailproxy")


async def search_emails(name: str, domain: str = "") -> list[str]:
    """Search the web for a business's published emails (directories, press, etc.).

    Prefers real people's emails over generic role addresses (info@/sales@).
    """
    from app.services.email_guess import is_generic

    queries = []
    if domain:
        queries.append(f'"{name}" "@{domain}"')
    queries += [
        f'"{name}" email contact',
        f'"{name}" owner OR founder OR president OR "general manager" email',
    ]

    found: list[str] = []
    for q in queries:
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
                r = await client.get(DDG_URL, params={"q": q}, timeout=20)
                r.raise_for_status()
        except Exception:
            continue
        for m in _EMAIL_RE.findall(r.text):
            e = m.lower()
            if any(j in e for j in _JUNK):
                continue
            if e not in found:
                found.append(e)
        if found:
            break

    # people first, generic role addresses last
    found.sort(key=is_generic)
    return found[:10]


async def rdap_email(domain: str) -> str | None:
    """Return the domain's registrant email via RDAP, if not privacy-protected."""
    domain = (domain or "").lower().removeprefix("www.")
    if not domain:
        return None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://rdap.org/domain/{domain}", timeout=15)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    for entity in data.get("entities", []):
        vcard = entity.get("vcardArray")
        items = vcard[1] if isinstance(vcard, list) and len(vcard) > 1 else []
        for item in items:
            if isinstance(item, list) and len(item) >= 4 and item[0] == "email":
                return item[3]
    return None
