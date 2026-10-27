"""Free website/email discovery: Brave Search API + DDG fallback + RDAP.

Brave Search API (free tier 2k/mo) is reliable; DuckDuckGo scraping is the
fallback when no key is set. RDAP (WHOIS) provides registrant emails.
"""
import re
import urllib.parse
from urllib.parse import urlparse

import httpx

from app.config import settings

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
CSE_URL = "https://www.googleapis.com/customsearch/v1"
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

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_JUNK = ("duckduckgo.com", "example.com", "sentry.io", "w3.org", "gmailproxy", "brave.com")


def _use_brave() -> bool:
    return bool(settings.brave_search_api_key)


def _use_cse() -> bool:
    return bool(settings.google_cse_key and settings.google_cse_cx)


async def _cse_search(query: str, count: int = 10) -> list[dict]:
    params = {
        "q": query,
        "key": settings.google_cse_key,
        "cx": settings.google_cse_cx,
        "num": min(count, 10),
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(CSE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    return [
        {"title": it.get("title", ""), "url": it.get("link", ""), "description": it.get("snippet", "")}
        for it in data.get("items", [])
    ]


async def _brave_search(query: str, count: int = 10) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.brave_search_api_key,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(BRAVE_URL, params={"q": query, "count": count}, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
    return data.get("web", {}).get("results", [])


async def _ddg_results(query: str) -> list[dict]:
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(DDG_URL, params={"q": query}, timeout=20)
        r.raise_for_status()
    out = []
    for m in re.finditer(r'uddg=([^"&]+)', r.text):
        out.append({"url": urllib.parse.unquote(m.group(1)), "description": r.text})
    return out


async def _search(query: str) -> list[dict]:
    if _use_cse():
        try:
            return await _cse_search(query)
        except Exception:
            pass
    if _use_brave():
        try:
            return await _brave_search(query)
        except Exception:
            pass
    return await _ddg_results(query)


async def search_domains(query: str, limit: int = 5) -> list[str]:
    results = await _search(query)
    domains: list[str] = []
    for res in results:
        dom = urlparse(res.get("url", "")).netloc.lower().removeprefix("www.")
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


async def search_emails(name: str, domain: str = "") -> list[str]:
    """Search the web for a business's published emails. Prefers people's emails."""
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
            results = await _search(q)
        except Exception:
            continue
        for res in results:
            text = " ".join([res.get("title", ""), res.get("description", ""), res.get("url", "")])
            for m in _EMAIL_RE.findall(text):
                e = m.lower()
                if any(j in e for j in _JUNK):
                    continue
                if e not in found:
                    found.append(e)
        if found:
            break

    found.sort(key=is_generic)
    return found[:10]


async def search_person_email(name: str, domain: str) -> str | None:
    """Search for a specific person's email at a domain (e.g. 'John Smith' @ acme.com)."""
    if not name or not domain:
        return None
    domain = domain.lower().removeprefix("www.")
    for q in [f'"{name}" "@{domain}"', f'"{name}" {domain} email']:
        try:
            results = await _search(q)
        except Exception:
            continue
        for res in results:
            text = " ".join([res.get("title", ""), res.get("description", ""), res.get("url", "")])
            for m in _EMAIL_RE.findall(text):
                e = m.lower()
                if e.endswith("@" + domain) and not any(j in e for j in _JUNK):
                    return e
    return None


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
