"""
AgentPay Sentinel — Router: Payments

POST /payments/evaluate            — main Trust Gateway evaluation endpoint
POST /payments/{decision_id}/approve — human approval of a REQUIRE_HUMAN_APPROVAL decision
POST /payments/{decision_id}/deny    — human denial of a REQUIRE_HUMAN_APPROVAL decision

Phase 3.3 changes:
  - /evaluate now uses the real authenticated session_id (SessionContext) instead
    of the previously hardcoded "sess_api"
  - /approve and /deny are fully implemented with:
      • ownership check
      • pending status check (replay protection)
      • expiry check
      • transaction-binding hash verification (for /approve)
      • sandbox payment execution (for /approve only)
      • tamper-evident audit events for all outcomes
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import (
    SessionContext,
    get_authorization_service,
    get_current_session_context,
    get_current_user,
    get_audit_service,
    get_pending_decision_service,
    get_session_store,
)
from ..models.audit import AuditEventType
from ..models.authorization import AuthorizationDecision, Decision, MockPaymentResult
from ..models.payment_intent import PaymentIntent, IntentStatus
from ..models.pending_decision import PendingDecision, PendingDecisionStatus
from ..models.user import User
from ..services.audit_service import AuditService
from ..services.authorization_service import AuthorizationService
from ..services.evidence_service import EvidenceService
from ..services.intent_service import IntentService
from ..services.payment_simulator import PaymentSimulator
from ..services.pending_decision_service import PendingDecisionService
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
        "Mock payment executes only on ALLOW. "
        "REQUIRE_HUMAN_APPROVAL decisions are persisted and can be approved/denied "
        "via POST /payments/{decision_id}/approve or /deny."
    ),
)
async def evaluate_payment(
    body: EvaluateRequest,
    session_ctx: Annotated[SessionContext, Depends(get_current_session_context)],
    authz_svc: Annotated[AuthorizationService, Depends(get_authorization_service)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> EvaluateResponse:
    """
    Evaluate a payment request through the full Trust Gateway pipeline.

    The real authenticated session_id is now propagated from the bearer token
    instead of the previously hardcoded 'sess_api'.
    """
    decision = await authz_svc.evaluate(
        user=session_ctx.user,
        session_id=session_ctx.session_id,   # Real session ID — no longer hardcoded
        raw_input=body.raw_input,
        evidence_id=body.evidence_id,
    )

    # Retrieve the audit event ID from the most recent event for this user
    events, _ = await audit_svc.get_events(user_id=session_ctx.user.user_id, limit=1)
    audit_event_id = events[0]["event_id"] if events else "unknown"

    return EvaluateResponse(authorization=decision, audit_event_id=audit_event_id)


@router.post(
    "/{decision_id}/approve",
    response_model=AuthorizationDecision,
    summary="Human-approve a pending payment",
    description=(
        "For REQUIRE_HUMAN_APPROVAL decisions only. "
        "A human reviewer approves the exact payment captured in the pending decision. "
        "Security checks enforced: ownership, pending status, expiry, and transaction binding. "
        "Approval ONLY authorises the exact transaction (payee, amount, currency, intent, evidence) "
        "that was evaluated — any change causes rejection. "
        "Payment simulation executes only after all checks pass. "
        "A second call with the same decision_id is rejected (replay protection)."
    ),
)
async def approve_payment(
    decision_id: str,
    body: HumanReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    pending_svc: Annotated[PendingDecisionService, Depends(get_pending_decision_service)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthorizationDecision:
    """
    Human approval flow:

    1. Load pending decision → 404 if not found
    2. Verify ownership     → 403 if wrong user
    3. Verify PENDING status → 409 if already finalised (replay protection)
    4. Verify not expired   → 410 if expired
    5. Verify transaction binding hash (no amount/payee/evidence change possible)
    6. Execute sandbox payment
    7. Mark decision EXECUTED
    8. Write HUMAN_APPROVED + PAYMENT_SIMULATED audit events
    9. Return AuthorizationDecision with human_approved=True
    """
    # Steps 1–5: all security checks in PendingDecisionService
    try:
        approved_pending = await pending_svc.approve(
            decision_id=decision_id,
            approving_user_id=current_user.user_id,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if msg.startswith("NOT_FOUND:"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        if msg.startswith("FORBIDDEN:"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg) from exc
        if msg.startswith("CONFLICT:"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        if msg.startswith("GONE:"):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=msg) from exc
        # Transaction binding failure or unexpected error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        ) from exc

    # Step 6: Execute sandbox payment using the IMMUTABLE intent snapshot
    # We reconstruct PaymentIntent from the stored snapshot (not from caller input)
    # to guarantee the payment is for the exact approved transaction.
    intent_data = approved_pending.intent_snapshot
    intent = PaymentIntent(**intent_data)

    simulator = PaymentSimulator()
    try:
        payment_result = await simulator.simulate(
            final_decision=Decision.ALLOW,
            intent=intent,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment simulation failed after approval: {exc}",
        ) from exc

    # Step 7: Mark decision EXECUTED
    await pending_svc.mark_executed(decision_id)

    # Step 8: Write tamper-evident audit events (HUMAN_APPROVED + PAYMENT_SIMULATED)
    approved_at = datetime.now(timezone.utc)
    await audit_svc.record(
        event_type=AuditEventType.HUMAN_APPROVED,
        user_id=current_user.user_id,
        session_id=approved_pending.session_id,
        intent_id=approved_pending.intent_id,
        evidence_id=approved_pending.evidence_id,
        decision_id=decision_id,
        decision=Decision.ALLOW.value,
        intent_snapshot=approved_pending.intent_snapshot,
        signals_snapshot=approved_pending.signals_snapshot,
        policy_snapshot=approved_pending.policy_snapshot,
        payment_result_snapshot=payment_result.model_dump(mode="json"),
    )
    await audit_svc.record(
        event_type=AuditEventType.PAYMENT_SIMULATED,
        user_id=current_user.user_id,
        session_id=approved_pending.session_id,
        intent_id=approved_pending.intent_id,
        evidence_id=approved_pending.evidence_id,
        decision_id=decision_id,
        decision=Decision.ALLOW.value,
        payment_result_snapshot=payment_result.model_dump(mode="json"),
    )

    # Step 9: Build and return AuthorizationDecision
    # Reconstruct signals from stored snapshot
    from ..models.signals import TransactionSignals
    signals = TransactionSignals(**approved_pending.signals_snapshot)

    return AuthorizationDecision(
        decision_id=decision_id,
        intent_id=approved_pending.intent_id,
        user_id=current_user.user_id,
        decision=Decision.ALLOW,
        reason=(
            approved_pending.policy_snapshot.get("reason", "Human approved.")
            + " [Human approved]"
        ),
        matched_rule_ids=approved_pending.policy_snapshot.get("matched_rule_ids", []),
        signals=signals,
        requires_human=False,
        human_approved=True,
        human_reviewed_at=approved_at,
        payment_result=payment_result,
        expires_at=approved_pending.expires_at,
        decided_at=approved_at,
    )


@router.post(
    "/{decision_id}/deny",
    response_model=AuthorizationDecision,
    summary="Human-deny a pending payment",
    description=(
        "For REQUIRE_HUMAN_APPROVAL decisions only. "
        "A human reviewer explicitly denies the payment. "
        "No payment is executed. "
        "Security checks enforced: ownership, pending status, and expiry. "
        "A second call with the same decision_id is rejected (replay protection). "
        "A tamper-evident audit event is written before the response is returned."
    ),
)
async def deny_payment(
    decision_id: str,
    body: HumanReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    pending_svc: Annotated[PendingDecisionService, Depends(get_pending_decision_service)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> AuthorizationDecision:
    """
    Human denial flow:

    1. Load pending decision → 404 if not found
    2. Verify ownership     → 403 if wrong user
    3. Verify PENDING status → 409 if already finalised
    4. Verify not expired   → 410 if expired
    5. Mark decision DENIED
    6. Write HUMAN_DENIED audit event
    7. Return AuthorizationDecision with human_approved=False (no payment)
    """
    # Steps 1–5: security checks + status transition
    try:
        denied_pending = await pending_svc.deny(
            decision_id=decision_id,
            denying_user_id=current_user.user_id,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if msg.startswith("NOT_FOUND:"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        if msg.startswith("FORBIDDEN:"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg) from exc
        if msg.startswith("CONFLICT:"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        if msg.startswith("GONE:"):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=msg) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        ) from exc

    # Step 6: Write tamper-evident HUMAN_DENIED audit event (no payment snapshot)
    denied_at = datetime.now(timezone.utc)
    await audit_svc.record(
        event_type=AuditEventType.HUMAN_DENIED,
        user_id=current_user.user_id,
        session_id=denied_pending.session_id,
        intent_id=denied_pending.intent_id,
        evidence_id=denied_pending.evidence_id,
        decision_id=decision_id,
        decision=Decision.DENY.value,
        intent_snapshot=denied_pending.intent_snapshot,
        signals_snapshot=denied_pending.signals_snapshot,
        policy_snapshot=denied_pending.policy_snapshot,
    )

    # Step 7: Return AuthorizationDecision — no payment result
    from ..models.signals import TransactionSignals
    signals = TransactionSignals(**denied_pending.signals_snapshot)

    return AuthorizationDecision(
        decision_id=decision_id,
        intent_id=denied_pending.intent_id,
        user_id=current_user.user_id,
        decision=Decision.DENY,
        reason=(
            denied_pending.policy_snapshot.get("reason", "Payment required human approval.")
            + " [Human denied]"
        ),
        matched_rule_ids=denied_pending.policy_snapshot.get("matched_rule_ids", []),
        signals=signals,
        requires_human=False,
        human_approved=False,
        human_reviewed_at=denied_at,
        payment_result=None,  # NEVER populated for denial
        expires_at=denied_pending.expires_at,
        decided_at=denied_at,
    )
