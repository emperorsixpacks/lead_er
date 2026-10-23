from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Lead
from app.schemas import LeadOut

router = APIRouter()


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    city: str | None = None,
    has_email: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Lead).order_by(Lead.created_at.desc())

    if q:
        stmt = stmt.where(
            text(
                "to_tsvector('english', coalesce(business_name,'') || ' ' || "
                "coalesce(category,'') || ' ' || coalesce(city,'') || ' ' || "
                "coalesce(address,'') || ' ' || coalesce(email,'')) "
                "@@ websearch_to_tsquery('english', :q)"
            )
        ).params(q=q)
    if status:
        stmt = stmt.where(Lead.status == status)
    if category:
        stmt = stmt.where(Lead.category.ilike(f"%{category}%"))
    if city:
        stmt = stmt.where(Lead.city.ilike(f"%{city}%"))
    if has_email is True:
        stmt = stmt.where(Lead.email.is_not(None), Lead.email != "")
    elif has_email is False:
        stmt = stmt.where(or_(Lead.email.is_(None), Lead.email == ""))

    stmt = stmt.limit(min(limit, 200)).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return rows
