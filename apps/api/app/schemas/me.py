from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ExplainLevel = Literal["eli5", "student", "expert"]


class Profile(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    locale: str
    explain_level: ExplainLevel
    plan: str
    is_admin: bool
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    explain_level: ExplainLevel | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    db: Literal["ok", "down", "unconfigured"]
    worker: Literal["running", "on_demand", "off"]
