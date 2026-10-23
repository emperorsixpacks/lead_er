import re
from urllib.parse import urljoin, urlparse

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
SOCIAL_HOSTS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com")
_PAGES = ("", "contact", "contact-us", "about", "about-us", "team")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def crawl(website: str) -> dict:
    """Crawl a business site for emails, social links and body text."""
    if not website:
        return {}
    if not website.startswith("http"):
        website = f"https://{website}"

    emails: set[str] = set()
    socials: dict[str, str] = {}
    text_parts: list[str] = []

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=USER_AGENT)
        page = await ctx.new_page()
        urls = [website] + [urljoin(website, f"/{p}") for p in _PAGES if p]
        for u in urls[:4]:
            try:
                await page.goto(u, timeout=20000, wait_until="domcontentloaded")
            except Exception:
                continue
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            if text:
                text_parts.append(text[:5000])
            for m in EMAIL_RE.findall(text):
                emails.add(m.lower())
            links = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a')).map(a => a.href)"
            )
            for href in links:
                try:
                    host = urlparse(href).netloc.lower()
                except Exception:
                    continue
                for s in SOCIAL_HOSTS:
                    if s in host:
                        socials[s.split(".")[0]] = href
        await browser.close()

    return {
        "emails": sorted(emails),
        "socials": socials,
        "site_text": " ".join(text_parts)[:15000],
    }
