from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_name: str | None = None
    category: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    website: str | None = None
    phone: str | None = None
    rating: float | None = None
    email: str | None = None
    email_status: str | None = None
    hook: str | None = None
    facts: dict[str, Any] | None = None
    source: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class EventIn(BaseModel):
    token: str
    type: str
    url: str | None = None
    ua: str | None = None
    ip: str | None = None
