"""
AgentPay Sentinel — Data Models
AuditEvent — Tamper-Evident Audit Trail

Design:
  event_hash   = SHA-256(canonical JSON of this event's payload)
  chained_hash = SHA-256(event_hash + prev_event_hash)

Any modification to a past event changes its event_hash, which invalidates
the chained_hash of every subsequent event, making tampering detectable.

Note: "tamper-evident audit trail" — not "immutable audit log".
Immutability is an infrastructure property (DynamoDB TTL off, S3 Object Lock).
Tamper-evidence is a cryptographic property we implement here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    SESSION_CREATED = "SESSION_CREATED"
    INTENT_EXTRACTED = "INTENT_EXTRACTED"
    EVIDENCE_UPLOADED = "EVIDENCE_UPLOADED"
    EVIDENCE_EXTRACTED = "EVIDENCE_EXTRACTED"
    SIGNALS_COMPUTED = "SIGNALS_COMPUTED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    AUTHORIZATION_DECISION = "AUTHORIZATION_DECISION"
    HUMAN_APPROVAL_REQUESTED = "HUMAN_APPROVAL_REQUESTED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_DENIED = "HUMAN_DENIED"
    PAYMENT_SIMULATED = "PAYMENT_SIMULATED"
    PAYMENT_DENIED = "PAYMENT_DENIED"


class AuditEvent(BaseModel):
    """
    One entry in the tamper-evident audit trail.
    Written to the store BEFORE the API response is returned (audit-first).

    Chain integrity is verified by recomputing:
      SHA-256(event_hash + prev_event_hash) == chained_hash
    and checking that prev_event_hash matches the previous event's event_hash.
    """

    event_id: str = Field(..., examples=["audit_mno678"])
    event_type: AuditEventType

    # Principal / session context
    user_id: str
    session_id: Optional[str] = Field(None)

    # Related entity references
    intent_id: Optional[str] = Field(None)
    evidence_id: Optional[str] = Field(None)
    decision_id: Optional[str] = Field(None)

    # Decision summary (for AUTHORIZATION_DECISION events)
    decision: Optional[str] = Field(None, description="ALLOW | DENY | REQUIRE_HUMAN_APPROVAL")

    # Full snapshots at time of event (complete auditability, no back-references)
    intent_snapshot: Optional[Dict[str, Any]] = Field(None)
    evidence_snapshot: Optional[Dict[str, Any]] = Field(None)
    signals_snapshot: Optional[Dict[str, Any]] = Field(None)
    policy_snapshot: Optional[Dict[str, Any]] = Field(None)
    payment_result_snapshot: Optional[Dict[str, Any]] = Field(None)

    # --- Tamper-evident chain ---
    # event_hash   = SHA-256(canonical JSON payload of this event, excluding hash fields)
    # prev_event_hash = event_hash of the immediately prior event for this user ("GENESIS" for first)
    # chained_hash = SHA-256(event_hash + prev_event_hash)
    event_hash: Optional[str] = Field(
        None,
        description="SHA-256 of this event's canonical JSON payload",
        examples=["sha256:abc123..."],
    )
    prev_event_hash: Optional[str] = Field(
        None,
        description="event_hash of the previous audit event for this user ('GENESIS' if first)",
        examples=["sha256:xyz789..."],
    )
    chained_hash: Optional[str] = Field(
        None,
        description="SHA-256(event_hash + prev_event_hash) — links events into a verifiable chain",
        examples=["sha256:def456..."],
    )

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
