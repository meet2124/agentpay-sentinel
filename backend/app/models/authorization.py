"""
AgentPay Sentinel — Data Models
AuthorizationDecision and MockPaymentResult

The decision comes from the deterministic policy engine.
The LLM is never the final authority.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .signals import TransactionSignals


class Decision(str, Enum):
    """Final authorization verdict from the Trust Gateway."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"


class MockPaymentResult(BaseModel):
    """
    Result of the sandbox payment simulator.

    This is ALWAYS clearly labeled.
    It is NEVER a real payment.
    It is NEVER produced for DENY or REQUIRE_HUMAN_APPROVAL decisions.
    """

    status: str = Field(
        default="SIMULATED_SUCCESS",
        description="SIMULATED_SUCCESS or SIMULATED_FAILURE. Never real.",
    )
    transaction_id: str = Field(..., examples=["MOCK-20260917-001"])
    payee: str
    amount: float
    currency: str = "INR"
    simulated_at: datetime = Field(default_factory=datetime.utcnow)
    disclaimer: str = Field(
        default=(
            "⚠️ SANDBOX SIMULATION ONLY. No real payment was made. "
            "AgentPay Sentinel does not connect to any real payment network or UPI system."
        ),
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class AuthorizationDecision(BaseModel):
    """
    Final authorization decision produced by the Trust Gateway.

    The decision field is set by the deterministic policy engine.
    Raw LLM text never directly sets this value.
    """

    decision_id: str = Field(..., examples=["dec_jkl345"])
    intent_id: str
    user_id: str

    # The verdict — set exclusively by policy_service
    decision: Decision
    reason: str = Field(
        ...,
        description="Human-readable explanation citing which signals triggered which rule",
    )
    matched_rule_ids: List[str] = Field(
        ...,
        description="Policy rule IDs that produced this decision",
        examples=[["deny_amount_mismatch", "deny_payee_mismatch"]],
    )

    # Full signal snapshot (what the policy engine read)
    signals: TransactionSignals

    # Human-in-the-loop
    requires_human: bool = Field(default=False)
    human_approved: Optional[bool] = Field(None)
    human_reviewed_at: Optional[datetime] = Field(None)

    # Payment result — only populated when decision == ALLOW
    payment_result: Optional[MockPaymentResult] = Field(
        None,
        description="Sandbox payment result. Present ONLY when decision is ALLOW.",
    )

    # Lifecycle
    expires_at: datetime
    decided_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
