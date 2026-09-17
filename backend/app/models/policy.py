"""
AgentPay Sentinel — Data Models
PolicyRule, PolicyResult, and the canonical MVP rule set.

Rules operate exclusively on named fields of TransactionSignals.
No rule condition references a floating-point score or a risk level enum.
First matching rule (lowest priority number) wins.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"


class PolicyRule(BaseModel):
    """A single deterministic authorization rule."""

    rule_id: str = Field(..., examples=["deny_amount_mismatch"])
    name: str = Field(...)
    description: str = Field(...)
    # Human-readable condition (informational — actual logic is in policy_service.py)
    condition: str = Field(...)
    action: PolicyDecision = Field(...)
    priority: int = Field(..., ge=1, description="Lower number = evaluated first")
    is_active: bool = Field(default=True)
    version: str = Field(default="1.0.0")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


class PolicyResult(BaseModel):
    """
    Result of evaluating the full policy rule set against TransactionSignals.
    Deterministic — no LLM involvement.
    """

    intent_id: str
    decision: PolicyDecision
    matched_rule_ids: List[str] = Field(...)
    evaluated_rule_count: int
    reason: str = Field(...)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ---------------------------------------------------------------------------
# Canonical MVP Policy Rule Set — source of truth for policy_service.py
# ---------------------------------------------------------------------------
# Conditions are expressed in plain English here; the code in policy_service.py
# implements the exact same logic using TransactionSignals fields.
# ---------------------------------------------------------------------------

MVP_POLICY_RULES: List[dict] = [
    {
        "rule_id": "deny_evidence_missing_high_amount",
        "name": "Deny: No Evidence, High Amount",
        "description": (
            "Deny transactions over ₹500 that have no supporting evidence. "
            "Small payments may proceed without evidence under rule 80."
        ),
        "condition": "NOT signals.evidence_present AND signals.intent.amount > 500",
        "action": "DENY",
        "priority": 10,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "deny_amount_mismatch",
        "name": "Deny: Amount Mismatch",
        "description": (
            "Deny when evidence is present but the agent's requested amount "
            "differs from the evidence amount beyond the ₹1 tolerance."
        ),
        "condition": "signals.evidence_present AND NOT signals.amount_match",
        "action": "DENY",
        "priority": 20,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "deny_payee_mismatch",
        "name": "Deny: Payee Mismatch",
        "description": (
            "Deny when evidence is present but the agent's intended payee "
            "does not sufficiently match the vendor named in the evidence "
            "(similarity < 0.85)."
        ),
        "condition": "signals.evidence_present AND NOT signals.payee_match",
        "action": "DENY",
        "priority": 30,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "deny_low_confidence_extraction",
        "name": "Deny: Low-Confidence Evidence Extraction",
        "description": (
            "Deny when evidence was provided but the extraction confidence "
            "is below 0.70, making the extracted data unreliable."
        ),
        "condition": "signals.evidence_present AND NOT signals.evidence_extraction_ok",
        "action": "DENY",
        "priority": 40,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "human_approval_exceeds_limit",
        "name": "Human Approval: Exceeds Spending Limit",
        "description": "Require human review when the amount exceeds the user's per-transaction spending limit.",
        "condition": "NOT signals.amount_within_limit",
        "action": "REQUIRE_HUMAN_APPROVAL",
        "priority": 50,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "human_approval_unknown_payee_medium_amount",
        "name": "Human Approval: Unknown Payee, Medium Amount",
        "description": (
            "Require human review when the payee has never been paid by this user "
            "and the amount exceeds ₹2,000."
        ),
        "condition": "NOT signals.payee_seen_before AND signals.intent.amount > 2000",
        "action": "REQUIRE_HUMAN_APPROVAL",
        "priority": 60,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "allow_full_match",
        "name": "Allow: Full Match",
        "description": (
            "Allow when amount and payee match evidence, evidence quality is acceptable, "
            "and the amount is within the user's spending limit."
        ),
        "condition": (
            "signals.amount_match AND signals.payee_match AND "
            "signals.evidence_present AND signals.amount_within_limit"
        ),
        "action": "ALLOW",
        "priority": 70,
        "is_active": True,
        "version": "1.0.0",
    },
    {
        "rule_id": "allow_small_no_evidence",
        "name": "Allow: Small Payment, No Evidence Required",
        "description": "Allow low-value payments (≤ ₹500) without evidence when within spending limit.",
        "condition": "NOT signals.evidence_present AND signals.intent.amount <= 500 AND signals.amount_within_limit",
        "action": "ALLOW",
        "priority": 80,
        "is_active": True,
        "version": "1.0.0",
    },
]
