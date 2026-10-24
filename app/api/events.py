from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Email, Event, Lead
from app.schemas import EventIn
from app.security import verify

router = APIRouter()

_SECRET = settings.api_secret.encode()

# Gmail's image proxy + prefetchers fire within seconds of send; flag as bot.
_BOT_WINDOW_SECONDS = 20
_PROXY_BOT_WINDOW_SECONDS = 60
_PROXY_SIGNATURES = ("GoogleImageProxy", "mail.app", "antispam")


@router.post("")
async def events(req: Request):
    raw = await req.body()
    sig = req.headers.get("x-sig", "")
    if not verify(raw, sig, _SECRET):
        raise HTTPException(status_code=401, detail="bad signature")

    payload = await req.json()
    e = EventIn.model_validate(payload)
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(Email.sent_at, Lead.id, Lead.business_name, Lead.category)
                .join(Lead, Lead.id == Email.lead_id)
                .where(Email.token == e.token)
            )
        ).first()

        if not row:
            return {"notify": False}

        sent_at, lead_id, business_name, category = row
        secs = (now - sent_at).total_seconds() if sent_at else 0
        ua = e.ua or ""
        # Only open/click are subject to proxy/prefetch bot heuristics.
        is_bot = e.type in ("open", "click") and (
            secs < _BOT_WINDOW_SECONDS
            or (any(sig in ua for sig in _PROXY_SIGNATURES) and secs < _PROXY_BOT_WINDOW_SECONDS)
        )

        db.add(
            Event(
                token=e.token,
                type=e.type,
                url=e.url,
                ua=ua,
                ip=e.ip,
                is_bot=is_bot,
            )
        )

        if not is_bot and e.type in ("open", "click", "reply", "bounce", "unsub"):
            # Only upgrade; a lower-priority event must not overwrite a higher one.
            new_status = {
                "open": "opened",
                "click": "clicked",
                "reply": "replied",
                "bounce": "bounced",
                "unsub": "unsub",
            }.get(e.type)
            prior = {
                "open": ("sent",),
                "click": ("sent", "opened"),
                "reply": ("sent", "opened", "clicked"),
                "bounce": ("sent", "opened", "clicked", "replied"),
                "unsub": ("sent", "opened", "clicked", "replied"),
            }.get(e.type, ())
            if new_status:
                await db.execute(
                    Lead.__table__.update()
                    .where(Lead.id == lead_id, Lead.status.in_(prior))
                    .values(status=new_status)
                )

        await db.commit()

    return {"notify": not is_bot, "business": business_name, "category": category}
