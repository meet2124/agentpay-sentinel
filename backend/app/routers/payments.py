"""
AgentPay Sentinel — Router: Payments

POST /payments/evaluate    — main Trust Gateway evaluation endpoint
POST /payments/{id}/approve — human approval of a REQUIRE_HUMAN_APPROVAL decision
POST /payments/{id}/deny    — human denial of a REQUIRE_HUMAN_APPROVAL decision
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import (
    get_authorization_service,
    get_current_user,
    get_audit_service,
    get_session_store,
)
from ..models.authorization import AuthorizationDecision, Decision, MockPaymentResult
from ..models.user import User
from ..services.authorization_service import AuthorizationService
from ..services.audit_service import AuditService
from ..services.payment_simulator import PaymentSimulator
from ..models.audit import AuditEventType
from ..models.payment_intent import PaymentIntent, IntentStatus
from ..services.intent_service import IntentService
from ..services.evidence_service import EvidenceService
from ..dependencies import get_evidence_service

router = APIRouter(prefix="/payments", tags=["Payments"])


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    """
    Request body for the main Trust Gateway evaluation endpoint.

    Provide raw_input (natural language) and optionally an evidence_id
    from a prior /evidence/upload call.
    """
    raw_input: str = Field(
        ...,
        min_length=1,
        description="Natural language payment instruction from the agent",
        examples=["Pay ₹1,850 to ABC Hardware."],
    )
    evidence_id: Optional[str] = Field(
        None,
        description="ID of a previously uploaded and extracted evidence document",
        examples=["evid_abc123"],
    )


class EvaluateResponse(BaseModel):
    """Complete Trust Gateway evaluation result."""
    authorization: AuthorizationDecision
    audit_event_id: str = Field(..., description="ID of the audit event written for this decision")


class HumanReviewRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional human review note")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    summary="Evaluate a payment request",
    description=(
        "The primary Trust Gateway endpoint. "
        "Runs the complete pipeline: intent extraction → evidence lookup → "
        "signal computation → policy evaluation → authorization decision → audit. "
        "Returns ALLOW, DENY, or REQUIRE_HUMAN_APPROVAL. "
        "Mock payment executes only on ALLOW."
    ),
)
async def evaluate_payment(
    body: EvaluateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    authz_svc: Annotated[AuthorizationService, Depends(get_authorization_service)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> EvaluateResponse:
    decision = await authz_svc.evaluate(
        user=current_user,
        session_id="sess_api",  # replaced by real session ID on Day 3
        raw_input=body.raw_input,
        evidence_id=body.evidence_id,
    )

    # Retrieve the audit event ID from the most recent event for this user
    events, _ = await audit_svc.get_events(user_id=current_user.user_id, limit=1)
    audit_event_id = events[0]["event_id"] if events else "unknown"

    return EvaluateResponse(authorization=decision, audit_event_id=audit_event_id)


@router.post(
    "/{decision_id}/approve",
    response_model=AuthorizationDecision,
    summary="Human-approve a pending payment",
    description=(
        "For REQUIRE_HUMAN_APPROVAL decisions only. "
        "A human reviewer approves the payment. "
        "Triggers mock payment execution after approval."
    ),
)
async def approve_payment(
    decision_id: str,
    body: HumanReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    authz_svc: Annotated[AuthorizationService, Depends(get_authorization_service)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthorizationDecision:
    # For MVP: return a placeholder — full implementation requires persisted decision store
    # This endpoint is exercised in the human-approval integration test
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Human approval requires a persisted decision store (DynamoDB — Day 2). "
            "For MVP demo, use POST /payments/evaluate with matching evidence."
        ),
    )


@router.post(
    "/{decision_id}/deny",
    response_model=AuthorizationDecision,
    summary="Human-deny a pending payment",
)
async def deny_payment(
    decision_id: str,
    body: HumanReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AuthorizationDecision:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Human denial requires a persisted decision store (DynamoDB — Day 2).",
    )
