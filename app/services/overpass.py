import httpx

ENDPOINT = "https://overpass-api.de/api/interpreter"


async def query(overpass_ql: str) -> list[dict]:
    """Run a raw Overpass QL query and return flattened element dicts."""
    async with httpx.AsyncClient() as client:
        r = await client.post(ENDPOINT, data={"data": overpass_ql}, timeout=60)
        r.raise_for_status()
        data = r.json()

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        results.append(
            {
                "business_name": name,
                "category": tags.get("amenity") or tags.get("shop") or tags.get("office"),
                "address": tags.get("addr:street"),
                "city": tags.get("addr:city"),
                "phone": tags.get("phone"),
                "website": tags.get("website"),
                "external_id": f"osm/{el['type']}/{el['id']}",
            }
        )
    return results


def bbox_query(category: str, south: float, west: float, north: float, east: float) -> str:
    """Build a query for a category inside a bounding box."""
    key, value = category.split(":", 1) if ":" in category else ("amenity", category)
    bbox = f"{south},{west},{north},{east}"
    return (
        f'[out:json][timeout:60];(node["{key}"="{value}"]({bbox});'
        f'way["{key}"="{value}"]({bbox}););out center 100;'
    )


async def search_name(fragment: str, south: float, west: float, north: float, east: float) -> list[dict]:
    """Search businesses whose name contains `fragment` inside a bounding box."""
    bbox = f"{south},{west},{north},{east}"
    ql = (
        f'[out:json][timeout:60];('
        f'nwr["name"~"{fragment}",i]({bbox});'
        f');out center 100;'
    )
    return await query(ql)
