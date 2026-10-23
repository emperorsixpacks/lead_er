"""Pipeline stages as plain async functions (no Celery).

discover -> enrich -> verify -> personalize -> send

Trigger them from HTTP endpoints (app.api.pipeline) or scripts/run_pipeline.py.
"""
import html
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Email, Lead
from app.services import gmail, llm, places, verifier
from app.services.enrich import crawl
from app.services.tracking import new_token, pixel_html, unsubscribe_url

SUPPRESSED = {"unsub", "bounced", "invalid"}


# ── Discover ──────────────────────────────────────────────────────────
async def discover(categories: list[str] | None = None, cities: list[str] | None = None) -> int:
    cats = categories or settings.categories
    cits = cities or settings.cities
    if not cats or not cits:
        return 0
    created = 0
    async with SessionLocal() as db:
        for city in cits:
            for cat in cats:
                for p in await places.search_text(f"{cat} in {city}"):
                    name = p.get("business_name")
                    if not name:
                        continue
                    exists = (
                        await db.execute(
                            select(Lead.id).where(Lead.business_name == name, Lead.city == city)
                        )
                    ).first()
                    if exists:
                        continue
                    db.add(
                        Lead(
                            business_name=name,
                            category=p.get("category"),
                            address=p.get("address"),
                            city=city.split(" ")[0].title(),
                            country=settings.target_country,
                            phone=p.get("phone"),
                            website=p.get("website"),
                            rating=p.get("rating"),
                            source="places",
                        )
                    )
                    created += 1
        await db.commit()
    return created


# ── Enrich ────────────────────────────────────────────────────────────
async def enrich_lead(lead_id: str) -> dict:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead or not lead.website:
            return {}
        data = await crawl(lead.website)
        emails = data.get("emails", [])
        if emails and not lead.email:
            lead.email = emails[0]
        lead.facts = {
            **(lead.facts or {}),
            "emails": emails,
            "socials": data.get("socials", {}),
            "site_text": data.get("site_text", ""),
        }
        lead.status = "enriched"
        await db.commit()
        return data


# ── Verify ────────────────────────────────────────────────────────────
async def verify_lead(lead_id: str) -> str:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead or not lead.email:
            return "no-email"
        result = await verifier.verify(lead.email)
        lead.email_status = result["status"]
        lead.status = "invalid" if result["status"] == "invalid" else "verified"
        await db.commit()
        return result["status"]


# ── Personalize ───────────────────────────────────────────────────────
async def personalize_lead(lead_id: str) -> dict:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return {}
        site_text = (lead.facts or {}).get("site_text", "") or lead.business_name or ""
        result = await llm.personalize(site_text)
        lead.hook = result.get("hook")
        facts = lead.facts or {}
        facts["facts"] = result.get("facts", [])
        lead.facts = facts
        lead.status = "personalized"
        await db.commit()
        return result


# ── Send ──────────────────────────────────────────────────────────────
SUBJECT_TEMPLATE = "{business} — quick question"
BODY_TEMPLATE = """<html><body>
<p>Hi {name},</p>
<p>{hook}</p>
<p>{facts_html}</p>
<p>Thanks,<br>{sender}</p>
<p style="color:#888;font-size:12px">
<a href="{unsub}">Unsubscribe</a> · {company} · {address}
</p>
</body></html>"""


def _render(lead: Lead, token: str) -> tuple[str, str]:
    subject = SUBJECT_TEMPLATE.format(business=lead.business_name or "your business")
    facts = (lead.facts or {}).get("facts", []) or []
    facts_html = "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"
    hook = lead.hook or f"I came across {lead.business_name or 'your business'} and wanted to reach out."
    body = BODY_TEMPLATE.format(
        name=lead.business_name or "there",
        hook=html.escape(hook),
        facts_html=facts_html,
        sender=html.escape(settings.sender_company or settings.gmail_smtp_user),
        unsub=unsubscribe_url(token),
        company=html.escape(settings.sender_company or ""),
        address=html.escape(settings.sender_address or ""),
    )
    body += pixel_html(token)
    return subject, body


async def send_lead(lead_id: str) -> str:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return "missing"
        if lead.status in SUPPRESSED or lead.email_status == "invalid" or not lead.email:
            return "suppressed"

        today = datetime.now(timezone.utc).date()
        sent_today = (
            await db.execute(
                select(func.count()).select_from(Email).where(func.date(Email.sent_at) == today)
            )
        ).scalar_one()
        if sent_today >= settings.daily_send_cap:
            return "cap-reached"

        token = new_token()
        subject, body = _render(lead, token)
        try:
            message_id, thread_id = gmail.send_email(lead.email, subject, body)
        except Exception as exc:
            return f"error:{exc}"

        db.add(
            Email(
                token=token,
                lead_id=lead.id,
                to_address=lead.email,
                subject=subject,
                gmail_message_id=message_id,
                gmail_thread_id=thread_id,
            )
        )
        lead.status = "sent"
        await db.commit()
        return "sent"


# ── Full pipeline ─────────────────────────────────────────────────────
async def run_pipeline(limit: int = 50) -> dict:
    async with SessionLocal() as db:
        new_leads = (
            await db.execute(
                select(Lead).where(Lead.status == "new").order_by(Lead.created_at.desc()).limit(limit)
            )
        ).scalars().all()

    results = {"enriched": 0, "verified": 0, "personalized": 0, "sent": 0, "suppressed": 0}
    for lead in new_leads:
        await enrich_lead(str(lead.id))
        results["enriched"] += 1
        await verify_lead(str(lead.id))
        results["verified"] += 1
        await personalize_lead(str(lead.id))
        results["personalized"] += 1
        outcome = await send_lead(str(lead.id))
        if outcome == "sent":
            results["sent"] += 1
        elif outcome == "suppressed":
            results["suppressed"] += 1
    return results
