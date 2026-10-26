"""USDA FSIS Meat, Poultry & Egg Product Inspection Directory.

Free, official list of every federally-inspected meat/poultry establishment in
the US: name, address, phone, and activity (Meat Processing, Poultry Slaughter,
etc.). No website/email, so we guess the domain from the name / DBAs and let
enrich crawl it.

Source: https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory
"""
import csv
import io
import re

import httpx

URL = "https://www.fsis.usda.gov/sites/default/files/media_file/documents/MPI_Directory_by_Establishment_Name.csv"

_ACTIVITY_KEYWORDS = (
    "Meat Processing", "Meat Slaughter", "Poultry Processing", "Poultry Slaughter",
    "Egg Processing", "Egg Products", "Certification", "Voluntary",
)


def _guess_domains(name: str, dbas: str) -> list[str]:
    raw = [name] + [d.strip() for d in (dbas or "").split(";") if d.strip()]
    out: list[str] = []
    for n in raw:
        # strip a leading "(City) - " prefix used for multi-plant companies
        n = re.sub(r"^\([^)]*\)\s*[-–—]?\s*", "", n.strip())
        # strip legal suffixes, case-insensitively
        n = re.sub(r"\b(inc|llc|co|corp|ltd|company|corporation|incorporated)\b\.?", "", n, flags=re.IGNORECASE)
        slug = re.sub(r"[^a-z0-9]", "", n.lower())
        domain = f"{slug}.com"
        if slug and domain not in out:
            out.append(domain)
    return out


async def fetch_establishments(limit: int | None = None) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(URL, timeout=60)
        r.raise_for_status()

    results: list[dict] = []
    for row in csv.DictReader(io.StringIO(r.text)):
        name = (row.get("establishment_name") or "").strip()
        if not name:
            continue
        domains = _guess_domains(name, row.get("dbas") or "")
        results.append(
            {
                "business_name": name,
                "category": (row.get("activities") or "").strip(),
                "address": (row.get("street") or "").strip(),
                "city": (row.get("city") or "").strip(),
                "country": "US",
                "phone": (row.get("phone") or "").strip(),
                "website": domains[0] if domains else None,
                "website_candidates": domains,
                "external_id": f"usda/{row.get('establishment_id') or row.get('establishment_number')}",
            }
        )
        if limit and len(results) >= limit:
            break
    return results
