"""
AgentPay Sentinel — Data Models
User model and UserTier enum

trust_score intentionally omitted: we evaluate individual TRANSACTIONS,
not the global trustworthiness of a human principal.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class UserTier(str, Enum):
    BASIC = "BASIC"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"


class User(BaseModel):
    """Authenticated user / session principal."""

    user_id: str = Field(..., description="Unique user identifier", examples=["usr_abc123"])
    name: str = Field(..., description="Display name", examples=["Priya Sharma"])
    email: str = Field(..., description="Email address", examples=["priya@example.com"])
    tier: UserTier = Field(default=UserTier.STANDARD, description="Account tier")

    # Financial limits (INR)
    spending_limit_inr: float = Field(
        ...,
        gt=0,
        description="Maximum single-transaction spending limit in INR",
        examples=[10000.00],
    )
    daily_limit_inr: Optional[float] = Field(
        None,
        description="Daily cumulative spending limit in INR",
        examples=[50000.00],
    )

    # Lifecycle
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class UserSession(BaseModel):
    """Active session for an authenticated user."""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: str
    token: str = Field(..., description="Bearer token for API authentication")
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Request / Response schemas ---

class SessionCreateRequest(BaseModel):
    user_id: str = Field(..., examples=["usr_abc123"])
    api_key: str = Field(..., examples=["sk-test-abc123"])


class SessionCreateResponse(BaseModel):
    session_id: str
    token: str
    expires_at: datetime
    user: User
