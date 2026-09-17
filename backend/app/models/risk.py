"""
AgentPay Sentinel — Data Models
RiskAssessment, RiskLevel, and RiskFlag models
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskFlag(str, Enum):
    AMOUNT_EXCEEDS_LIMIT = "AMOUNT_EXCEEDS_LIMIT"
    AMOUNT_NEAR_LIMIT = "AMOUNT_NEAR_LIMIT"
    UNKNOWN_PAYEE = "UNKNOWN_PAYEE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    EVIDENCE_LOW_CONFIDENCE = "EVIDENCE_LOW_CONFIDENCE"
    HIGH_AMOUNT_ANOMALY = "HIGH_AMOUNT_ANOMALY"
    OFF_HOURS = "OFF_HOURS"
    RAPID_SUCCESSION = "RAPID_SUCCESSION"
    LOW_USER_TRUST_SCORE = "LOW_USER_TRUST_SCORE"


def risk_level_from_score(score: int) -> RiskLevel:
    """Convert a numeric risk score (0–100) to a RiskLevel enum."""
    if score >= 80:
        return RiskLevel.CRITICAL
    elif score >= 60:
        return RiskLevel.HIGH
    elif score >= 35:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


class RiskFactors(BaseModel):
    """
    Decomposed risk factor values used to compute the overall score.
    All factors are normalized to [0, 1] where 1 = highest risk contribution.
    """

    amount_vs_limit_ratio: float = Field(
        ...,
        ge=0.0,
        description="intent.amount / user.spending_limit (>1.0 means over limit)",
        example=0.185,
    )
    payee_seen_before: bool = Field(
        ...,
        description="Whether this payee has been paid before by this user",
        example=True,
    )
    evidence_consistency: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="EvidenceMatch.consistency_score (higher = lower risk)",
        example=0.96,
    )
    is_business_hours: bool = Field(
        ...,
        description="Whether the request was made during business hours (IST 9am–6pm weekdays)",
        example=True,
    )
    amount_anomaly: bool = Field(
        ...,
        description="Whether the amount is a statistical outlier for this user's history",
        example=False,
    )
    user_trust_score_normalized: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="user.trust_score / 100 (higher = lower risk)",
        example=0.85,
    )
    rapid_succession: bool = Field(
        default=False,
        description="Whether this is the second+ payment in a short window",
    )


class RiskAssessment(BaseModel):
    """
    Computed risk profile for a PaymentIntent.
    Produced by the deterministic risk scoring engine.
    LLM output is an *input* to this computation, not the output.
    """

    risk_id: str = Field(..., example="risk_ghi012")
    intent_id: str = Field(..., description="Associated PaymentIntent ID")
    user_id: str

    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall risk score from 0 (no risk) to 100 (critical risk)",
        example=18,
    )
    level: RiskLevel = Field(..., description="Risk level derived from score", example=RiskLevel.LOW)
    flags: List[RiskFlag] = Field(
        default_factory=list,
        description="List of specific risk flags that were triggered",
    )
    factors: RiskFactors = Field(..., description="Decomposed risk factor values")
    notes: Optional[str] = Field(None, description="Human-readable risk summary")

    assessed_at: datetime = Field(default_factory=datetime.utcnow)
