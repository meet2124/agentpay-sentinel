"""
AgentPay Sentinel — Data Models
PendingDecision — Persisted record for REQUIRE_HUMAN_APPROVAL decisions.

Security design:
  - Created once at policy evaluation time with an immutable transaction snapshot
  - The transaction_binding_hash binds the approval to the EXACT transaction
    (payee, amount, currency, intent_id, evidence_id). Any field change → new hash.
  - Status transitions are one-way: PENDING → APPROVED | DENIED
  - An APPROVED decision can transition to EXECUTED after payment simulation
  - Expired decisions cannot be approved (expires_at enforced in Python + DynamoDB TTL)
  - A second approval on the same decision_id is rejected (replay protection)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class PendingDecisionStatus(str, Enum):
    """Lifecycle states for a pending human-approval decision."""
    PENDING  = "PENDING"   # awaiting human review
    APPROVED = "APPROVED"  # human approved; payment execution in progress
    DENIED   = "DENIED"    # human explicitly denied
    EXPIRED  = "EXPIRED"   # TTL elapsed before human acted (logical state)
    EXECUTED = "EXECUTED"  # payment simulator ran successfully after approval


class PendingDecision(BaseModel):
    """
    Immutable snapshot of a REQUIRE_HUMAN_APPROVAL decision.

    All transaction-critical fields (payee, amount, currency, intent_id,
    evidence_id) are captured at creation time and bound by
    transaction_binding_hash.  Approval of this record ONLY authorises the
    exact transaction described here — not any other transaction.
    """

    # --- Identity ---
    decision_id: str = Field(..., description="Unique decision identifier (dec_…)")
    user_id:     str = Field(..., description="Owning user — the only user who may approve/deny")
    session_id:  str = Field(..., description="Session in which the evaluation was requested")
    intent_id:   str = Field(..., description="Associated PaymentIntent identifier")

    # --- Exact transaction fields (immutable at creation) ---
    amount:   float = Field(..., description="Exact payment amount in INR")
    currency: str   = Field(..., description="ISO 4217 currency code")
    payee:    str   = Field(..., description="Exact payee name")

    # --- Full immutable snapshots (for audit + binding verification) ---
    intent_snapshot:  Dict[str, Any] = Field(..., description="Full PaymentIntent at decision time")
    signals_snapshot: Dict[str, Any] = Field(..., description="Full TransactionSignals at decision time")
    policy_snapshot:  Dict[str, Any] = Field(..., description="Full PolicyResult at decision time")
    evidence_id: Optional[str] = Field(None, description="Evidence ID if any evidence was attached")

    # --- Transaction binding ---
    transaction_binding_hash: str = Field(
        ...,
        description=(
            "SHA-256 over canonical {intent_id, payee, amount, currency, evidence_id}. "
            "Recomputed and verified at approval time. Any field change = hash mismatch = rejection."
        ),
    )

    # --- Lifecycle ---
    status:     PendingDecisionStatus = Field(default=PendingDecisionStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="Decision expires at this time (1 hour from creation)")

    # --- Resolution timestamps ---
    approved_at: Optional[datetime] = Field(None)
    denied_at:   Optional[datetime] = Field(None)
    executed_at: Optional[datetime] = Field(None)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
