"""Pipeline stages as plain async functions (no Celery).

discover -> enrich -> verify -> personalize -> send

Trigger them from HTTP endpoints (app.api.pipeline) or scripts/run_pipeline.py.
"""
import html
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Email, Lead
from app.services import gmail, llm, places, verifier, websearch
from app.services.email_guess import extract_people, guess_emails, guess_generic, is_generic, _split
from app.services.enrich import crawl
from app.services.geocode import geocode_city
from app.services import overpass
from app.services.report import build_pdf
from app.services.tracking import new_token, pixel_html, unsubscribe_url

logger = logging.getLogger("lead_er")

SUPPRESSED = {"unsub", "bounced", "invalid"}


def _city_name(city: str) -> str:
    return city.split(" ")[0].title()


def _singular(cat: str) -> str:
    c = cat.strip().lower()
    if c.endswith("ies") and len(c) > 4:
        return c[:-3] + "y"  # companies -> company
    if c.endswith("es") and len(c) > 3:
        return c[:-2]  # businesses -> business
    if c.endswith("s") and len(c) > 3:
        return c[:-1]  # roofers -> roofer, plumbers -> plumber
    return c


# ── Discover ──────────────────────────────────────────────────────────
async def discover(categories: list[str] | None = None, cities: list[str] | None = None) -> int:
    cats = categories or settings.categories
    cits = cities or settings.cities
    if not cats or not cits:
        return 0
    created = 0
    async with SessionLocal() as db:
        async def add(item: dict, city: str, source: str) -> bool:
            nonlocal created
            name = item.get("business_name")
            if not name:
                return False
            # Skip empty nodes (street names, non-businesses): no website and no phone.
            if not item.get("website") and not item.get("phone"):
                return False
            exists = (
                await db.execute(
                    select(Lead.id).where(Lead.business_name == name, Lead.city == _city_name(city))
                )
            ).first()
            if exists:
                return False
            db.add(
                Lead(
                    business_name=name,
                    category=item.get("category"),
                    address=item.get("address"),
                    city=_city_name(city),
                    country=settings.target_country,
                    phone=item.get("phone"),
                    website=item.get("website"),
                    rating=item.get("rating"),
                    source=source,
                )
            )
            created += 1
            return True

        for city in cits:
            # Bounding box for the city (Nominatim, free) — shared by Overpass.
            try:
                bbox = await geocode_city(city)
            except Exception:
                bbox = None

            for cat in cats:
                frag = _singular(cat)

                # Primary (free, no key): OpenStreetMap Overpass.
                if bbox:
                    try:
                        tags = overpass.category_tags(frag)
                        if tags:
                            items = await overpass.search_tags(
                                tags, bbox["south"], bbox["west"], bbox["north"], bbox["east"]
                            )
                        else:
                            items = await overpass.search_name(
                                frag, bbox["south"], bbox["west"], bbox["north"], bbox["east"]
                            )
                    except Exception:
                        items = []
                    for item in items:
                        await add(item, city, "overpass")

                # Optional (paid, needs key): Google Places text search.
                if settings.google_maps_api_key:
                    try:
                        results = await places.search_text(f"{cat} in {city}")
                    except Exception:
                        results = []
                    for p in results:
                        await add(p, city, "places")

        await db.commit()
    return created


# ── USDA FSIS (meat/poultry establishments) ───────────────────────────
async def discover_usda(limit: int | None = None) -> int:
    """Import meat/poultry establishments from the USDA FSIS directory."""
    from app.services import usda

    items = await usda.fetch_establishments(limit)
    created = 0
    async with SessionLocal() as db:
        existing = {
            name
            for (name,) in (await db.execute(select(Lead.business_name))).all()
        }
        for item in items:
            name = item["business_name"]
            if name in existing:
                continue
            candidates = item.pop("website_candidates", [])
            db.add(
                Lead(
                    business_name=name,
                    category=item.get("category"),
                    address=item.get("address"),
                    city=item.get("city"),
                    country=item.get("country"),
                    phone=item.get("phone"),
                    website=item.get("website"),
                    facts={"website_candidates": candidates} if candidates else None,
                    source="usda",
                )
            )
            existing.add(name)
            created += 1
        await db.commit()
    return created


# ── Enrich ────────────────────────────────────────────────────────────
async def enrich_lead(lead_id: str) -> dict:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead or not lead.website:
            return {}
        try:
            data = await crawl(lead.website)
        except Exception as exc:
            return {"error": f"crawl:{exc.__class__.__name__}"}
        emails = data.get("emails", [])
        site_text = data.get("site_text", "")
        domain = urlparse(lead.website).netloc

        # Free fallback when the guessed domain had nothing: RDAP (WHOIS) on the
        # domain, then a search to find the real website.
        if not emails:
            try:
                reg_email = await websearch.rdap_email(domain)
                if reg_email:
                    emails = [reg_email]
            except Exception:
                pass
        if not emails:
            try:
                real = await websearch.resolve_website(lead.business_name or "", lead.city or "")
                if real and real != domain:
                    data2 = await crawl(f"https://{real}")
                    if data2.get("emails"):
                        emails = data2["emails"]
                        lead.website = f"https://{real}"
                        domain = real
                    if data2.get("site_text"):
                        site_text = data2["site_text"]
            except Exception:
                pass
        if not emails:
            # Last resort: search the web for the business's published emails.
            try:
                emails = await websearch.search_emails(lead.business_name or "", domain)
            except Exception:
                pass

        # Founder/owner detection + email pattern guessing when no address was published.
        people = extract_people(site_text)
        candidates: list[str] = []
        for person in people[:3]:
            first, last = _split(person["name"])
            candidates += guess_emails(domain, first, last)
        # Generic catch-all addresses (info@, contact@, ...) are common for SMBs.
        if not emails:
            candidates += guess_generic(domain)
        candidates = list(dict.fromkeys(c for c in candidates if c))

        # Final guard: drop emails from other companies' domains (search noise).
        # Keep @gmail.com person emails and anything matching the lead's own site.
        site_domains = set()
        for w in (lead.website, f"https://{domain}"):
            d = urlparse(w or "").netloc.lower().removeprefix("www.")
            if d:
                site_domains.add(d)
        emails = [
            e
            for e in emails
            if e.endswith("@gmail.com") or any(e.endswith("@" + d) for d in site_domains)
        ]

        # Prioritize: real person emails before generic role addresses.
        emails = sorted(emails, key=is_generic)

        if emails and not lead.email:
            lead.email = emails[0]
        lead.facts = {
            **(lead.facts or {}),
            "emails": emails,
            "email_candidates": candidates,
            "people": people,
            "socials": data.get("socials", {}),
            "site_text": site_text,
        }
        lead.status = "enriched"
        await db.commit()
        return data


# ── Verify ────────────────────────────────────────────────────────────
async def verify_lead(lead_id: str, max_candidates: int = 5) -> str:
    """Verify the lead's email, trying guessed candidates until one validates.

    Cost is per email, so cap the number of candidates checked.
    """
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return "missing"
        facts = lead.facts or {}
        candidates = [lead.email] + list(facts.get("email_candidates") or [])
        candidates = list(dict.fromkeys(c for c in candidates if c))[:max_candidates]
        if not candidates:
            return "no-email"

        best, best_status = None, None
        for email in candidates:
            result = await verifier.verify(email)
            if result["status"] == "valid":
                best, best_status = email, "valid"
                break
            if best is None:
                best, best_status = email, result["status"]

        lead.email = best
        lead.email_status = best_status
        lead.status = "invalid" if best_status == "invalid" else "verified"
        await db.commit()
        return best_status


# ── Personalize ───────────────────────────────────────────────────────
async def personalize_lead(lead_id: str) -> dict:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return {}
        site_text = (lead.facts or {}).get("site_text", "") or ""
        try:
            result = await llm.personalize(
                business_name=lead.business_name or "",
                category=lead.category or "",
                city=lead.city or "",
                site_text=site_text,
            )
        except Exception as exc:
            logger.exception("personalize failed for %s", lead.business_name)
            return {"error": f"llm:{exc.__class__.__name__}"}
        lead.hook = result.get("hook")
        facts = lead.facts or {}
        facts["facts"] = result.get("facts", [])
        facts["subject_line"] = result.get("subject_line", "")
        facts["contact_name"] = result.get("contact_name", "")
        lead.facts = facts
        lead.status = "personalized"
        await db.commit()
        return result


# ── Send ──────────────────────────────────────────────────────────────
SUBJECT_TEMPLATE = "{business} — quick question"


def _render(lead: Lead, token: str) -> tuple[str, str]:
    subject = (lead.facts or {}).get("subject_line") or SUBJECT_TEMPLATE.format(
        business=lead.business_name or "your business"
    )
    facts = (lead.facts or {}).get("facts", []) or []
    facts_html = (
        "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"
        if facts
        else ""
    )
    hook = lead.hook or f"I came across {lead.business_name or 'your business'} and wanted to reach out."
    contact_name = (lead.facts or {}).get("contact_name", "") or ""
    # Greet the person if we know their first name, else the business.
    first_name = contact_name.strip().split(" ")[0] if contact_name.strip() else ""
    name = first_name or (lead.business_name or "there")
    sender = settings.sender_name or settings.sender_company or settings.gmail_smtp_user

    def link(label: str, url: str) -> str:
        return f'<p><a href="{html.escape(url)}">{html.escape(label)}</a></p>' if url else ""

    value_prop = f"<p>{html.escape(settings.email_value_prop)}</p>" if settings.email_value_prop else ""
    demo_block = link("Watch a 3-minute demo", settings.email_demo_url)
    booking_block = link("Book a 15-minute call", settings.email_booking_url)
    linkedin_block = link("LinkedIn", settings.email_linkedin_url)
    cta = f"<p>{html.escape(settings.email_cta)}</p>" if settings.email_cta else ""

    # Footer: company/address only when set; unsubscribe optional (config flag).
    footer_parts = []
    if settings.email_include_unsubscribe:
        footer_parts.append(f'<a href="{unsubscribe_url(token)}">Unsubscribe</a>')
    if settings.sender_company:
        footer_parts.append(html.escape(settings.sender_company))
    if settings.sender_address:
        footer_parts.append(html.escape(settings.sender_address))
    footer_html = (
        f'<p style="color:#888;font-size:12px">{" · ".join(footer_parts)}</p>'
        if footer_parts
        else ""
    )

    body = (
        "<html><body>"
        f"<p>Hi {html.escape(name)},</p>"
        f"<p>{html.escape(hook)}</p>"
        f"{value_prop}"
        f"{facts_html}"
        f"{demo_block}"
        f"{booking_block}"
        f"{cta}"
        "<p>If you're not the right person for this, could you point me to whoever is?</p>"
        f"<p>Thanks,<br>{html.escape(sender)}</p>"
        f"{linkedin_block}"
        f"{footer_html}"
        "</body></html>"
    )
    if settings.email_include_pixel:
        body += pixel_html(token)
    return subject, body


def _render_text(lead: Lead) -> tuple[str, str]:
    """Plain-text version of the email (for the PDF / manual copy-paste)."""
    subject = (lead.facts or {}).get("subject_line") or SUBJECT_TEMPLATE.format(
        business=lead.business_name or "your business"
    )
    facts = (lead.facts or {}).get("facts", []) or []
    hook = lead.hook or f"I came across {lead.business_name or 'your business'} and wanted to reach out."
    contact_name = (lead.facts or {}).get("contact_name", "") or ""
    first_name = contact_name.strip().split(" ")[0] if contact_name.strip() else ""
    name = first_name or (lead.business_name or "there")
    sender = settings.sender_name or settings.sender_company or settings.gmail_smtp_user

    lines = [f"Hi {name},", "", hook]
    if settings.email_value_prop:
        lines += ["", settings.email_value_prop]
    if facts:
        lines += ["", *[f"- {f}" for f in facts]]
    if settings.email_demo_url:
        lines += ["", f"Watch a 3-minute demo: {settings.email_demo_url}"]
    if settings.email_booking_url:
        lines += ["", f"Book a 15-minute call: {settings.email_booking_url}"]
    if settings.email_cta:
        lines += ["", settings.email_cta]
    lines += [
        "",
        "If you're not the right person for this, could you point me to whoever is?",
        "",
        "Thanks,",
        sender,
    ]
    if settings.email_linkedin_url:
        lines.append(settings.email_linkedin_url)

    return subject, "\n".join(lines)


async def send_lead(lead_id: str) -> str:
    async with SessionLocal() as db:
        lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
        if not lead:
            return "missing"
        if lead.status in SUPPRESSED or lead.email_status == "invalid" or not lead.email:
            return "suppressed"

        addr = lead.email.strip().lower()

        # Anti-spam: never email an address that bounced or unsubscribed on ANY lead.
        suppressed = (
            await db.execute(
                select(Lead.id)
                .where(func.lower(Lead.email) == addr, Lead.status.in_(("unsub", "bounced")))
                .limit(1)
            )
        ).first()
        if suppressed:
            return "suppressed"

        # Anti-spam: never email an address we've already contacted (any lead).
        already_sent = (
            await db.execute(
                select(Email.token).where(func.lower(Email.to_address) == addr).limit(1)
            )
        ).first()
        if already_sent:
            return "already-sent"

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
            message_id, thread_id = gmail.send_email(
                lead.email, subject, body, bcc=settings.send_bcc_email or None
            )
        except Exception as exc:
            logger.exception("send_lead failed for %s -> %s", lead.business_name, lead.email)
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
async def draft_report(limit: int = 20) -> dict:
    """Enrich + personalize leads, build a PDF of drafts, email it to you.

    You then send the emails yourself from your normal Gmail (no spam filter).
    """
    async with SessionLocal() as db:
        leads = (
            await db.execute(
                select(Lead)
                .where(Lead.source == "usda", Lead.status == "new", Lead.website.is_not(None))
                .order_by(Lead.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    drafts: list[dict] = []
    for lead in leads:
        await enrich_lead(str(lead.id))
        await personalize_lead(str(lead.id))
        async with SessionLocal() as db:
            l = (await db.execute(select(Lead).where(Lead.id == lead.id))).scalar_one()
            if not l.email:
                continue
            # Prefer the founder/owner's personal email over a generic info@/hello@.
            contact = (l.facts or {}).get("contact_name", "") or ""
            domain = urlparse(l.website or "").netloc
            if contact and is_generic(l.email):
                try:
                    person_email = await websearch.search_person_email(contact, domain)
                    if person_email:
                        l.email = person_email
                        await db.commit()
                except Exception:
                    pass
            subject, body = _render_text(l)
            drafts.append(
                {
                    "business_name": l.business_name,
                    "category": l.category,
                    "email": l.email,
                    "subject": subject,
                    "body": body,
                }
            )

    pdf_bytes = build_pdf(drafts) if drafts else None
    sent_to = settings.report_email or settings.send_bcc_email
    if pdf_bytes and sent_to:
        gmail.send_pdf_report(sent_to, f"lead_er drafts ({len(drafts)} leads)", pdf_bytes, "lead_er_drafts.pdf")
    return {"leads_processed": len(leads), "drafts": len(drafts), "sent_to": sent_to}


async def run_pipeline(limit: int = 50) -> dict:
    async with SessionLocal() as db:
        new_leads = (
            await db.execute(
                select(Lead).where(Lead.status == "new").order_by(Lead.created_at.desc()).limit(limit)
            )
        ).scalars().all()

    results = {"enriched": 0, "verified": 0, "personalized": 0, "sent": 0, "suppressed": 0, "duplicate": 0}
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
        elif outcome == "already-sent":
            results["duplicate"] += 1
    return results


async def scheduled_run(limit: int = 30) -> dict:
    """Discover new leads, then run them through the full pipeline.

    Called by the Cloudflare Worker's cron trigger.
    """
    discovered = await discover()
    results = await run_pipeline(limit)
    results["discovered"] = discovered
    return results
