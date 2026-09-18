"""
AgentPay Sentinel — Service: Pending Decision Lifecycle

Manages the full lifecycle of REQUIRE_HUMAN_APPROVAL decisions:
  1. create_pending_decision  — persist immutable record after policy decision
  2. get_pending_decision     — retrieve by decision_id
  3. approve                  — enforce ownership, expiry, binding, replay checks;
                                return approved record (payment execution in router)
  4. deny                     — enforce ownership, pending status checks;
                                return denied record

SECURITY INVARIANTS (all enforced in this service, not in the router):
  - Only the owning user_id may approve or deny a decision
  - An expired decision cannot be approved
  - A non-PENDING decision cannot be approved or denied (replay protection)
  - Transaction binding hash is verified at approval time — any change to
    payee, amount, currency, intent_id, or evidence_id causes rejection
  - No payment is ever executed here — execution is the router's responsibility
    AFTER receiving a successfully approved PendingDecision
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from ..adapters.base import PendingDecisionStoreAdapter
from ..models.pending_decision import PendingDecision, PendingDecisionStatus
from ..models.payment_intent import PaymentIntent
from ..models.policy import PolicyResult
from ..models.signals import TransactionSignals
from ..utils.crypto import compute_transaction_binding_hash

logger = logging.getLogger(__name__)


class PendingDecisionService:
    """
    Lifecycle manager for pending human-approval decisions.

    All security checks are performed here, not in the router, so they are
    testable independently of FastAPI.
    """

    def __init__(self, store: PendingDecisionStoreAdapter) -> None:
        self._store = store

    # ─────────────────────────────────────────────────────────────────────────
    # Create
    # ─────────────────────────────────────────────────────────────────────────

    async def create_pending_decision(
        self,
        *,
        decision_id: str,
        user_id: str,
        session_id: str,
        intent: PaymentIntent,
        signals: TransactionSignals,
        policy_result: PolicyResult,
        evidence_id: Optional[str],
        created_at: datetime,
        expires_at: datetime,
    ) -> PendingDecision:
        """
        Persist an immutable pending-decision record.

        Called IMMEDIATELY after policy evaluation returns REQUIRE_HUMAN_APPROVAL,
        before the audit event is written (so the record exists if the
        Lambda is re-invoked for the approval endpoint).

        The transaction_binding_hash is computed over the canonical form of
        {intent_id, payee, amount, currency, evidence_id} and stored
        alongside the full snapshot. It will be re-verified at approval time.
        """
        binding_hash = compute_transaction_binding_hash(
            intent_id=intent.intent_id,
            payee=intent.payee,
            amount=intent.amount,
            currency=intent.currency,
            evidence_id=evidence_id,
        )

        pending = PendingDecision(
            decision_id=decision_id,
            user_id=user_id,
            session_id=session_id,
            intent_id=intent.intent_id,
            amount=intent.amount,
            currency=intent.currency,
            payee=intent.payee,
            intent_snapshot=intent.model_dump(mode="json"),
            signals_snapshot=signals.model_dump(mode="json"),
            policy_snapshot=policy_result.model_dump(mode="json"),
            evidence_id=evidence_id,
            transaction_binding_hash=binding_hash,
            status=PendingDecisionStatus.PENDING,
            created_at=created_at,
            expires_at=expires_at,
        )

        record = pending.model_dump(mode="json")
        await self._store.put_pending_decision(record)

        logger.info(
            "Pending decision created",
            extra={
                "decision_id": decision_id,
                "user_id_prefix": user_id[:8],
                "binding_hash_prefix": binding_hash[:16],
                "expires_at": expires_at.isoformat(),
            },
        )
        return pending

    # ─────────────────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────────────────

    async def get_pending_decision(
        self, decision_id: str
    ) -> Optional[PendingDecision]:
        """
        Retrieve a pending decision by decision_id.
        Returns None if not found.
        Does NOT perform expiry or ownership checks — callers must check.
        """
        record = await self._store.get_pending_decision(decision_id)
        if record is None:
            return None
        return PendingDecision(**record)

    # ─────────────────────────────────────────────────────────────────────────
    # Approve
    # ─────────────────────────────────────────────────────────────────────────

    async def approve(
        self,
        *,
        decision_id: str,
        approving_user_id: str,
    ) -> PendingDecision:
        """
        Validate and approve a pending human-approval decision.

        Security checks (all must pass — first failure raises):
          1. Decision exists               → RuntimeError (caller maps to 404)
          2. Ownership matches             → RuntimeError (caller maps to 403)
          3. Status is PENDING             → RuntimeError (caller maps to 409)
          4. Not expired                   → RuntimeError (caller maps to 410)
          5. Transaction binding valid     → RuntimeError (caller maps to 422)
          6. Atomic store update succeeds  → RuntimeError (store handles replay)

        Returns the updated PendingDecision with status=APPROVED.
        Payment execution is performed by the caller AFTER this returns.
        """
        pending = await self._load_and_check(decision_id, approving_user_id)

        # Re-verify transaction binding hash from the immutable snapshot
        stored_hash = pending.transaction_binding_hash
        recomputed_hash = compute_transaction_binding_hash(
            intent_id=pending.intent_snapshot["intent_id"],
            payee=pending.intent_snapshot["payee"],
            amount=pending.intent_snapshot["amount"],
            currency=pending.intent_snapshot["currency"],
            evidence_id=pending.evidence_id,
        )
        if stored_hash != recomputed_hash:
            # This should never happen in normal operation — stored snapshot is
            # immutable. A mismatch indicates data corruption or tampering.
            logger.error(
                "SECURITY: Transaction binding hash mismatch on approval — "
                "stored snapshot may be corrupted or tampered with.",
                extra={"decision_id": decision_id},
            )
            raise RuntimeError(
                f"Transaction binding verification failed for decision {decision_id}. "
                "The stored transaction snapshot does not match its binding hash. "
                "Approval rejected."
            )

        now = datetime.now(timezone.utc)
        # Atomically mark APPROVED in the store (ConditionalExpression prevents replay)
        await self._store.update_pending_decision(
            decision_id,
            {
                "status":      PendingDecisionStatus.APPROVED.value,
                "approved_at": now.isoformat(),
            },
        )

        logger.info(
            "Pending decision approved",
            extra={
                "decision_id": decision_id,
                "user_id_prefix": approving_user_id[:8],
            },
        )

        return PendingDecision(
            **{
                **pending.model_dump(mode="json"),
                "status": PendingDecisionStatus.APPROVED,
                "approved_at": now,
            }
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Mark executed
    # ─────────────────────────────────────────────────────────────────────────

    async def mark_executed(
        self, decision_id: str, executed_at: Optional[datetime] = None
    ) -> None:
        """
        Mark an APPROVED decision as EXECUTED after payment simulation succeeds.

        Uses an atomic store.mark_executed() that conditions on status == APPROVED.
        A concurrent call to this method will be rejected by the store's conditional
        write (ConditionalCheckFailedException on DynamoDB, RuntimeError on local).

        This replaces the previous non-atomic get + put_pending_decision overwrite.
        """
        ts = (executed_at or datetime.now(timezone.utc)).isoformat()
        try:
            await self._store.mark_executed(decision_id, ts)
        except RuntimeError:
            logger.warning(
                "mark_executed rejected (decision not APPROVED or already EXECUTED — "
                "concurrent execution attempt?)",
                extra={"decision_id": decision_id},
            )
            raise

        logger.info(
            "Pending decision marked EXECUTED",
            extra={"decision_id": decision_id},
        )


    # ─────────────────────────────────────────────────────────────────────────
    # Deny
    # ─────────────────────────────────────────────────────────────────────────

    async def deny(
        self,
        *,
        decision_id: str,
        denying_user_id: str,
    ) -> PendingDecision:
        """
        Deny a pending human-approval decision.

        Security checks:
          1. Decision exists   → RuntimeError (caller maps to 404)
          2. Ownership matches → RuntimeError (caller maps to 403)
          3. Status is PENDING → RuntimeError (caller maps to 409)
          4. Not expired       → RuntimeError (caller maps to 410)
          5. Atomic store update (ConditionalExpression)

        Returns the updated PendingDecision with status=DENIED.
        No payment is ever executed for a denied decision.
        """
        pending = await self._load_and_check(decision_id, denying_user_id)

        now = datetime.now(timezone.utc)
        await self._store.update_pending_decision(
            decision_id,
            {
                "status":   PendingDecisionStatus.DENIED.value,
                "denied_at": now.isoformat(),
            },
        )

        logger.info(
            "Pending decision denied",
            extra={
                "decision_id": decision_id,
                "user_id_prefix": denying_user_id[:8],
            },
        )

        return PendingDecision(
            **{
                **pending.model_dump(mode="json"),
                "status":   PendingDecisionStatus.DENIED,
                "denied_at": now,
            }
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _load_and_check(
        self, decision_id: str, acting_user_id: str
    ) -> PendingDecision:
        """
        Common pre-flight checks for approve() and deny().

        Raises RuntimeError with a descriptive message for each failure case.
        The router maps these to appropriate HTTP status codes.
        """
        pending = await self.get_pending_decision(decision_id)

        # Check 1: Exists
        if pending is None:
            raise RuntimeError(f"NOT_FOUND: Pending decision '{decision_id}' not found.")

        # Check 2: Ownership
        if pending.user_id != acting_user_id:
            raise RuntimeError(
                f"FORBIDDEN: Decision '{decision_id}' belongs to a different user. "
                "You may only approve or deny your own pending decisions."
            )

        # Check 3: Pending status (replay protection)
        if pending.status != PendingDecisionStatus.PENDING:
            raise RuntimeError(
                f"CONFLICT: Decision '{decision_id}' is not in PENDING state "
                f"(current status: {pending.status.value}). "
                "Already-finalised decisions cannot be re-approved or re-denied."
            )

        # Check 4: Expiry
        now = datetime.now(timezone.utc)
        expires_at = pending.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            raise RuntimeError(
                f"GONE: Decision '{decision_id}' expired at {expires_at.isoformat()}. "
                "Please submit a new payment request."
            )

        return pending
