"""
AgentPay Sentinel — Data Models
TransactionSignals — the explicit boolean/enum signals that drive the policy engine.

These replace an opaque floating-point risk score as the authorization input.
Every signal is computed deterministically from intent + evidence + user context.
No LLM output directly sets any signal value.

display_risk_score is a DERIVED PRESENTATION VALUE only — it is computed last
and has zero effect on any policy condition.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TransactionSignals(BaseModel):
    """
    Explicit, named signals computed by comparison_service.
    These are the sole inputs to the policy engine.
    """

    intent_id: str
    evidence_id: Optional[str] = Field(None, description="ID of attached evidence, if any")

    # --- Amount ---
    amount_match: bool = Field(
        ...,
        description="True if |intent.amount - evidence.amount| <= AMOUNT_MATCH_THRESHOLD_INR",
    )
    amount_delta_inr: float = Field(
        ...,
        description="Absolute difference between intent amount and evidence amount in INR",
        examples=[0.00],
    )

    # --- Payee ---
    payee_match: bool = Field(
        ...,
        description="True if fuzzy_similarity(intent.payee, evidence.vendor_name) >= PAYEE_MATCH_THRESHOLD",
    )
    payee_similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fuzzy string similarity score between intent payee and evidence vendor (0–1)",
        examples=[0.94],
    )

    # --- Evidence presence and quality ---
    evidence_present: bool = Field(
        ...,
        description="True if a non-empty Evidence object was provided",
    )
    evidence_extraction_ok: bool = Field(
        ...,
        description="True if extraction_confidence >= EVIDENCE_CONFIDENCE_THRESHOLD",
    )
    evidence_extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Raw extraction confidence from the document parser (0–1)",
        examples=[0.94],
    )

    # --- Currency ---
    currency_match: bool = Field(
        ...,
        description="True if intent.currency exactly matches evidence.currency",
    )

    # --- Spending limit ---
    amount_within_limit: bool = Field(
        ...,
        description="True if intent.amount <= user.spending_limit_inr",
    )
    amount_vs_limit_ratio: float = Field(
        ...,
        ge=0.0,
        description="intent.amount / user.spending_limit_inr  (>1.0 means over limit)",
        examples=[0.185],
    )

    # --- Payee history ---
    payee_seen_before: bool = Field(
        ...,
        description="True if this user has previously paid this payee (from payee history store)",
    )

    # --- Presentation only (NOT used in any policy condition) ---
    display_risk_score: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "UI-only derived indicator. "
            "Higher = more signals triggered. "
            "NOT referenced in any policy rule."
        ),
        examples=[12],
    )

    computed_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
