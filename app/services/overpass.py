import httpx

# Overpass mirrors, ordered fastest/most reliable first. The main instance
# (overpass-api.de) rate-limits heavily, so we keep it last and fail over fast.
ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "lead_er/0.1 (https://github.com/emperorsixpacks/lead_er)"}
_TIMEOUT = 20

# Category keyword -> OpenStreetMap (key, value) tag pairs to search.
# Falls back to a name-substring search when a category is not listed.
CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "plumber": [("craft", "plumber"), ("office", "plumber")],
    "roofer": [("craft", "roofer"), ("office", "roofer")],
    "hvac": [("craft", "hvac"), ("office", "hvac"), ("craft", "heating_engineer")],
    "landscaper": [("craft", "landscaper"), ("craft", "gardener"), ("office", "landscaper")],
    "electrician": [("craft", "electrician")],
    "dentist": [("amenity", "dentist")],
    "doctor": [("amenity", "doctors"), ("amenity", "clinic")],
    "lawyer": [("office", "lawyer"), ("office", "notary")],
    "accountant": [("office", "accountant")],
    "real estate": [("office", "estate_agent")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "gym": [("leisure", "fitness_centre"), ("shop", "gym")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "auto repair": [("shop", "car_repair")],
    "cleaning": [("craft", "cleaner"), ("office", "cleaning")],
    "painter": [("craft", "painter")],
    "photographer": [("craft", "photographer")],
    "wholesaler": [("shop", "wholesale"), ("shop", "trade")],
    "butcher": [("craft", "butcher"), ("shop", "butcher")],
    "seafood": [("shop", "seafood")],
}

_CATEGORY_KEYS = ("amenity", "shop", "office", "craft", "tourism", "leisure")


def category_tags(category: str) -> list[tuple[str, str]] | None:
    return CATEGORY_TAGS.get(category.strip().lower())


def _address(tags: dict) -> str | None:
    num = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    return f"{num} {street}".strip() or None


def _city(tags: dict) -> str | None:
    return (
        tags.get("addr:city")
        or tags.get("addr:town")
        or tags.get("addr:village")
    )


def _category(tags: dict) -> str | None:
    for key in _CATEGORY_KEYS:
        if key in tags:
            return tags[key]
    return None


def _normalize(el: dict) -> dict | None:
    tags = el.get("tags", {})
    name = tags.get("name")
    if not name:
        return None
    return {
        "business_name": name,
        "category": _category(tags),
        "address": _address(tags),
        "city": _city(tags),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website"),
        "external_id": f"osm/{el['type']}/{el['id']}",
    }


async def query(overpass_ql: str) -> list[dict]:
    """Run a raw Overpass QL query and return normalized business dicts."""
    last: Exception | None = None
    for endpoint in ENDPOINTS:
        try:
            async with httpx.AsyncClient(headers=HEADERS) as client:
                r = await client.post(endpoint, data={"data": overpass_ql}, timeout=_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            return [
                norm
                for el in data.get("elements", [])
                if (norm := _normalize(el)) is not None
            ]
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise last or RuntimeError("all Overpass endpoints failed")


def _bbox(south: float, west: float, north: float, east: float) -> str:
    return f"{south},{west},{north},{east}"


async def search_tags(
    tags: list[tuple[str, str]], south: float, west: float, north: float, east: float
) -> list[dict]:
    bbox = _bbox(south, west, north, east)
    blocks = "".join(f'nwr["{k}"="{v}"]({bbox});' for k, v in tags)
    ql = f"[out:json][timeout:25];({blocks});out center 100;"
    return await query(ql)


async def search_name(
    fragment: str, south: float, west: float, north: float, east: float
) -> list[dict]:
    bbox = _bbox(south, west, north, east)
    ql = f'[out:json][timeout:25];(nwr["name"~"{fragment}",i]({bbox}););out center 100;'
    return await query(ql)
