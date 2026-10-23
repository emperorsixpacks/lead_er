import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_city(city: str) -> dict | None:
    """Resolve a 'City State' string to a bounding box via Nominatim.

    Returns {'south','west','north','east','display_name'} or None.
    Nominatim requires a descriptive User-Agent; keep requests sparse.
    """
    headers = {"User-Agent": "lead_er/0.1 (lead-generation tool)"}
    params = {"q": city, "format": "json", "limit": 1, "addressdetails": 0}
    async with httpx.AsyncClient() as client:
        r = await client.get(NOMINATIM_URL, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
    if not data:
        return None
    bb = data[0].get("boundingbox")
    if not bb or len(bb) < 4:
        return None
    south, north, west, east = (float(x) for x in bb[:4])
    return {
        "south": south,
        "west": west,
        "north": north,
        "east": east,
        "display_name": data[0].get("display_name"),
    }
