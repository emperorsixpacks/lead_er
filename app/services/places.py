import httpx

from app.config import settings

# Google Places API (New) Text Search.
URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = (
    "places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
    "places.websiteUri,places.rating,places.primaryType,places.id"
)


async def search_text(query: str, page_size: int = 20) -> list[dict]:
    """Run a Places text search (e.g. 'plumbers in Austin TX'). Returns normalized dicts."""
    if not settings.google_maps_api_key:
        return []
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": FIELDS,
        "Content-Type": "application/json",
    }
    body = {"textQuery": query, "pageSize": page_size}
    async with httpx.AsyncClient() as client:
        r = await client.post(URL, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    results = []
    for p in data.get("places", []):
        results.append(
            {
                "business_name": p.get("displayName", {}).get("text"),
                "category": p.get("primaryType"),
                "address": p.get("formattedAddress"),
                "phone": p.get("nationalPhoneNumber"),
                "website": p.get("websiteUri"),
                "rating": p.get("rating"),
                "external_id": p.get("id"),
            }
        )
    return results
