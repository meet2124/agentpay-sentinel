"""
AgentPay Sentinel — Data Models
PaymentIntent model and IntentStatus enum
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class IntentStatus(str, Enum):
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_DENIED = "HUMAN_DENIED"
    EXPIRED = "EXPIRED"


class PaymentMethod(str, Enum):
    UPI = "UPI"
    NEFT = "NEFT"
    IMPS = "IMPS"
    RTGS = "RTGS"
    UNKNOWN = "UNKNOWN"


class PaymentIntent(BaseModel):
    """
    Structured representation of a payment request.
    Extracted from natural language by the intent service (LLM stub → Bedrock later).
    Treated as UNTRUSTED until schema-validated here.
    """

    intent_id: str = Field(..., description="Unique intent identifier", examples=["intent_xyz789"])
    user_id: str = Field(..., description="Owning user ID")
    session_id: str = Field(..., description="Session in which intent was created")

    # Raw input preserved for audit
    raw_input: str = Field(
        ...,
        description="Original natural language instruction from the agent",
        examples=["Pay ₹1,850 to ABC Hardware."],
    )

    # Extracted structured fields — validated below
    payee: str = Field(..., min_length=1, description="Payee name", examples=["ABC Hardware"])
    amount: float = Field(..., gt=0, description="Payment amount", examples=[1850.00])
    currency: str = Field(default="INR", min_length=3, max_length=3, description="ISO 4217 currency code")
    purpose: Optional[str] = Field(None, description="Stated purpose of payment")
    payment_method: PaymentMethod = Field(default=PaymentMethod.UPI)

    # Extraction metadata
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0–1)",
        examples=[0.97],
    )
    extraction_model: str = Field(
        default="stub",
        description="Model used for extraction (stub | bedrock/claude-3-sonnet)",
    )

    # Lifecycle
    status: IntentStatus = Field(default=IntentStatus.PENDING_AUTHORIZATION)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="When this intent expires")

    @field_validator("payee")
    @classmethod
    def payee_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("payee must not be blank")
        return v.strip()

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# --- Request / Response schemas ---

class IntentCreateRequest(BaseModel):
    """Body for POST /payments/initiate — intent portion."""

    raw_input: str = Field(
        ...,
        min_length=1,
        description="Natural language payment instruction",
        examples=["Pay ₹1,850 to ABC Hardware."],
    )
    evidence_id: Optional[str] = Field(
        None,
        description="Pre-uploaded evidence ID to attach",
        examples=["evid_def456"],
    )
