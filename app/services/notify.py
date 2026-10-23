import httpx

from app.config import settings


async def push(title: str, body: str, priority: str = "default") -> None:
    if not settings.ntfy_topic:
        return
    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                url,
                json={"topic": settings.ntfy_topic, "title": title, "message": body, "priority": priority},
            )
    except Exception:
        pass
