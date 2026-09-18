"""
AgentPay Sentinel — Service: Authorization Orchestrator

Pipeline:
  1. Validate session → User
  2. Extract PaymentIntent from raw_input (LLM stub)
  3. Look up Evidence (if evidence_id provided)
  4. Fetch payee history (for payee_seen_before signal)
  5. Compute TransactionSignals (deterministic)
  6. Evaluate policy rules (deterministic) → PolicyResult
  7. Write tamper-evident audit event (BEFORE returning response)
  8. Execute mock payment IF AND ONLY IF decision == ALLOW
  9. Return AuthorizationDecision

LLM output is schema-validated at steps 2 and 3.
Raw LLM text never reaches step 6 (policy evaluation).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..adapters.base import SessionStoreAdapter
from ..models.audit import AuditEventType
from ..models.authorization import AuthorizationDecision, Decision, MockPaymentResult
from ..models.evidence import Evidence
from ..models.payment_intent import PaymentIntent
from ..models.user import User
from .audit_service import AuditService
from .comparison_service import ComparisonService
from .evidence_service import EvidenceService
from .intent_service import IntentService
from .payment_simulator import PaymentSimulator
from .pending_decision_service import PendingDecisionService
from .policy_service import PolicyService

logger = logging.getLogger(__name__)


class AuthorizationService:
    def __init__(
        self,
        intent_service: IntentService,
        evidence_service: EvidenceService,
        comparison_service: ComparisonService,
        policy_service: PolicyService,
        audit_service: AuditService,
        payment_simulator: PaymentSimulator,
        session_store: SessionStoreAdapter,
        pending_decision_svc: PendingDecisionService,
    ) -> None:
        self._intent_svc = intent_service
        self._evidence_svc = evidence_service
        self._comparison_svc = comparison_service
        self._policy_svc = policy_service
        self._audit_svc = audit_service
        self._simulator = payment_simulator
        self._session_store = session_store
        self._pending_svc = pending_decision_svc

    async def evaluate(
        self,
        *,
        user: User,
        session_id: str,
        raw_input: str,
        evidence_id: Optional[str] = None,
        # For direct evaluation tests — allow passing a pre-built intent + evidence
        _intent_override: Optional[PaymentIntent] = None,
        _evidence_override: Optional[Evidence] = None,
    ) -> AuthorizationDecision:
        """
        Run the complete Trust Gateway pipeline for a payment request.
        Returns an AuthorizationDecision with full signal and audit information.
        """

        # Step 1: Extract intent (or use override for testing)
        if _intent_override:
            intent = _intent_override
        else:
            intent = await self._intent_svc.extract_intent(
                raw_input=raw_input,
                user_id=user.user_id,
                session_id=session_id,
            )

        # Step 2: Look up evidence (or use override)
        evidence: Optional[Evidence] = None
        if _evidence_override:
            evidence = _evidence_override
        elif evidence_id:
            evidence = await self._evidence_svc.get_evidence(evidence_id)

        # Step 3: Fetch payee history for payee_seen_before signal
        payee_history = await self._session_store.get_payee_history(user.user_id)

        # Step 4: Compute explicit signals — DETERMINISTIC, no LLM
        signals = self._comparison_svc.compute_signals(
            intent=intent,
            evidence=evidence,
            user=user,
            payee_history=payee_history,
        )

        # Step 5: Evaluate policy rules — DETERMINISTIC, no LLM
        policy_result = self._policy_svc.evaluate(signals=signals, intent=intent)

        # Map PolicyDecision → Decision
        decision = Decision(policy_result.decision.value)

        # Build decision ID
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        decided_at = datetime.now(timezone.utc)
        expires_at = decided_at + timedelta(hours=1)

        # Structured decision log — no PII, no exact amounts
        # Amount is bucketed for CloudWatch metrics without exposing exact values
        _amount = intent.amount
        if _amount <= 500:
            amount_band = "0-500"
        elif _amount <= 1000:
            amount_band = "501-1000"
        elif _amount <= 5000:
            amount_band = "1001-5000"
        elif _amount <= 10000:
            amount_band = "5001-10000"
        else:
            amount_band = "10001+"

        logger.info(
            "authorization_decision",
            extra={
                "event": "authorization_decision",
                "user_id_prefix": user.user_id[:8],   # partial ID only
                "decision": decision.value,
                "matched_rule": policy_result.matched_rule_ids[0] if policy_result.matched_rule_ids else "none",
                "amount_band_inr": amount_band,
                "evidence_present": signals.evidence_present,
                "payee_seen_before": signals.payee_seen_before,
                "decision_id": decision_id,
            },
        )

        # Step 6: Persist pending decision when REQUIRE_HUMAN_APPROVAL
        # This must happen BEFORE the audit event so the record exists for /approve.
        if decision == Decision.REQUIRE_HUMAN_APPROVAL:
            await self._pending_svc.create_pending_decision(
                decision_id=decision_id,
                user_id=user.user_id,
                session_id=session_id,
                intent=intent,
                signals=signals,
                policy_result=policy_result,
                evidence_id=evidence.evidence_id if evidence else None,
                created_at=decided_at,
                expires_at=expires_at,
            )

        # Step 7: Execute mock payment ONLY if ALLOW
        payment_result: Optional[MockPaymentResult] = None
        if decision == Decision.ALLOW:
            payment_result = await self._simulator.simulate(
                final_decision=decision,
                intent=intent,
            )
            # Record payee in history after successful authorization
            await self._session_store.record_payee(user.user_id, intent.payee)

        # Step 8: Write tamper-evident audit event BEFORE returning response
        await self._audit_svc.record(
            event_type=AuditEventType.AUTHORIZATION_DECISION,
            user_id=user.user_id,
            session_id=session_id,
            intent_id=intent.intent_id,
            evidence_id=evidence.evidence_id if evidence else None,
            decision_id=decision_id,
            decision=decision.value,
            intent_snapshot=intent.model_dump(mode="json"),
            evidence_snapshot=evidence.model_dump(mode="json") if evidence else None,
            signals_snapshot=signals.model_dump(mode="json"),
            policy_snapshot=policy_result.model_dump(mode="json"),
            payment_result_snapshot=(
                payment_result.model_dump(mode="json") if payment_result else None
            ),
        )

        # Also write a dedicated HUMAN_APPROVAL_REQUESTED event for REQUIRE_HUMAN_APPROVAL.
        # This provides a clear, queryable audit record that human review was triggered.
        if decision == Decision.REQUIRE_HUMAN_APPROVAL:
            await self._audit_svc.record(
                event_type=AuditEventType.HUMAN_APPROVAL_REQUESTED,
                user_id=user.user_id,
                session_id=session_id,
                intent_id=intent.intent_id,
                evidence_id=evidence.evidence_id if evidence else None,
                decision_id=decision_id,
                decision=decision.value,
                intent_snapshot=intent.model_dump(mode="json"),
                signals_snapshot=signals.model_dump(mode="json"),
                policy_snapshot=policy_result.model_dump(mode="json"),
            )

        # Step 9: Build and return AuthorizationDecision
        return AuthorizationDecision(
            decision_id=decision_id,
            intent_id=intent.intent_id,
            user_id=user.user_id,
            decision=decision,
            reason=policy_result.reason,
            matched_rule_ids=policy_result.matched_rule_ids,
            signals=signals,
            requires_human=(decision == Decision.REQUIRE_HUMAN_APPROVAL),
            payment_result=payment_result,
            expires_at=expires_at,
            decided_at=decided_at,
        )
