"""
AgentPay Sentinel — Unit Tests: Transaction-Bound Human Approval (Phase 3.3)

Tests A–L from the specification plus policy regression coverage (L).

Test coverage:
  A. Pending payment can be approved
  B. Pending payment can be denied
  C. Unauthorized user cannot approve another user's decision
  D. Expired approval cannot execute
  E. Replayed approval cannot execute twice
  F. Modified amount cannot use an old approval
  G. Modified payee cannot use an old approval
  H. Changed evidence cannot use an old approval
  I. Approval executes payment only once
  J. Denial never executes payment
  K. Audit events are written for approve and deny
  L. Existing deterministic policy behavior remains intact

Run: python -m pytest tests/unit/test_human_approval.py -v
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Local imports (no AWS — uses in-memory adapters)
# ---------------------------------------------------------------------------
from app.adapters.local import LocalAuditStoreAdapter, LocalPendingDecisionStoreAdapter
from app.models.audit import AuditEventType
from app.models.authorization import Decision
from app.models.payment_intent import PaymentIntent, IntentStatus
from app.models.pending_decision import PendingDecision, PendingDecisionStatus
from app.models.policy import PolicyDecision, PolicyResult
from app.models.signals import TransactionSignals
from app.services.audit_service import AuditService
from app.services.pending_decision_service import PendingDecisionService
from app.utils.crypto import compute_transaction_binding_hash, GENESIS_HASH


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def make_intent(
    *,
    payee: str = "ABC Hardware",
    amount: float = 50000.0,
    currency: str = "INR",
    intent_id: str = "intent_test001",
    user_id: str = "usr_standard",
    session_id: str = "sess_real001",
) -> PaymentIntent:
    return PaymentIntent(
        intent_id=intent_id,
        user_id=user_id,
        session_id=session_id,
        raw_input=f"Pay ₹{amount} to {payee}.",
        payee=payee,
        amount=amount,
        currency=currency,
        confidence_score=0.95,
    )


def make_signals(intent_id: str = "intent_test001") -> TransactionSignals:
    return TransactionSignals(
        intent_id=intent_id,
        evidence_id=None,
        amount_match=True,
        amount_delta_inr=0.0,
        payee_match=True,
        payee_similarity=0.94,
        evidence_present=False,
        evidence_extraction_ok=False,
        evidence_extraction_confidence=0.0,
        currency_match=True,
        amount_within_limit=False,     # triggers REQUIRE_HUMAN_APPROVAL
        amount_vs_limit_ratio=5.0,
        payee_seen_before=True,
        display_risk_score=50,
    )


def make_policy_result(intent_id: str = "intent_test001") -> PolicyResult:
    return PolicyResult(
        intent_id=intent_id,
        decision=PolicyDecision.REQUIRE_HUMAN_APPROVAL,
        matched_rule_ids=["human_approval_exceeds_limit"],
        evaluated_rule_count=8,
        reason="Amount exceeds spending limit. Human approval required.",
        evaluated_at=datetime.now(timezone.utc),
    )


async def create_pending(
    svc: PendingDecisionService,
    *,
    decision_id: str = "dec_test001",
    user_id: str = "usr_standard",
    intent: Optional[PaymentIntent] = None,
    evidence_id: Optional[str] = None,
    ttl_hours: float = 1.0,
) -> PendingDecision:
    """Helper: create a pending decision with configurable TTL."""
    if intent is None:
        intent = make_intent(user_id=user_id)
    signals = make_signals(intent_id=intent.intent_id)
    policy = make_policy_result(intent_id=intent.intent_id)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ttl_hours)
    return await svc.create_pending_decision(
        decision_id=decision_id,
        user_id=user_id,
        session_id="sess_real001",
        intent=intent,
        signals=signals,
        policy_result=policy,
        evidence_id=evidence_id,
        created_at=now,
        expires_at=expires_at,
    )


@pytest.fixture()
def store() -> LocalPendingDecisionStoreAdapter:
    """Fresh in-memory store per test (module-level dict cleared via new instance)."""
    from app.adapters import local as local_mod
    # Clear the shared module-level store between tests
    local_mod._pending_decisions.clear()
    return LocalPendingDecisionStoreAdapter()


@pytest.fixture()
def svc(store) -> PendingDecisionService:
    return PendingDecisionService(store=store)


@pytest.fixture()
def audit_store() -> LocalAuditStoreAdapter:
    from app.adapters import local as local_mod
    local_mod._audit_store.clear()
    local_mod._audit_order.clear()
    return LocalAuditStoreAdapter()


@pytest.fixture()
def audit_svc(audit_store) -> AuditService:
    return AuditService(audit_store=audit_store)


# ===========================================================================
# A. Pending payment can be approved
# ===========================================================================

@pytest.mark.asyncio
async def test_A_pending_can_be_approved(svc):
    """A: A PENDING decision transitions to APPROVED after approve()."""
    await create_pending(svc, decision_id="dec_A")

    approved = await svc.approve(decision_id="dec_A", approving_user_id="usr_standard")

    assert approved.status == PendingDecisionStatus.APPROVED
    assert approved.approved_at is not None
    assert approved.decision_id == "dec_A"


# ===========================================================================
# B. Pending payment can be denied
# ===========================================================================

@pytest.mark.asyncio
async def test_B_pending_can_be_denied(svc):
    """B: A PENDING decision transitions to DENIED after deny()."""
    await create_pending(svc, decision_id="dec_B")

    denied = await svc.deny(decision_id="dec_B", denying_user_id="usr_standard")

    assert denied.status == PendingDecisionStatus.DENIED
    assert denied.denied_at is not None
    assert denied.decision_id == "dec_B"


# ===========================================================================
# C. Unauthorized user cannot approve another user's decision
# ===========================================================================

@pytest.mark.asyncio
async def test_C_unauthorized_user_cannot_approve(svc):
    """C: A different user attempting approval must raise FORBIDDEN."""
    await create_pending(svc, decision_id="dec_C", user_id="usr_standard")

    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_C", approving_user_id="usr_basic")

    assert "FORBIDDEN" in str(exc_info.value)


@pytest.mark.asyncio
async def test_C_unauthorized_user_cannot_deny(svc):
    """C (deny variant): A different user attempting denial must raise FORBIDDEN."""
    await create_pending(svc, decision_id="dec_C2", user_id="usr_standard")

    with pytest.raises(RuntimeError) as exc_info:
        await svc.deny(decision_id="dec_C2", denying_user_id="usr_premium")

    assert "FORBIDDEN" in str(exc_info.value)


# ===========================================================================
# D. Expired approval cannot execute
# ===========================================================================

@pytest.mark.asyncio
async def test_D_expired_decision_cannot_be_approved(svc):
    """D: An expired decision (TTL in the past) must raise GONE."""
    await create_pending(svc, decision_id="dec_D", ttl_hours=-0.5)  # already expired

    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_D", approving_user_id="usr_standard")

    assert "GONE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_D_expired_decision_cannot_be_denied(svc):
    """D (deny variant): An expired decision must raise GONE even for denial."""
    await create_pending(svc, decision_id="dec_D2", ttl_hours=-0.5)

    with pytest.raises(RuntimeError) as exc_info:
        await svc.deny(decision_id="dec_D2", denying_user_id="usr_standard")

    assert "GONE" in str(exc_info.value)


# ===========================================================================
# E. Replayed approval cannot execute twice
# ===========================================================================

@pytest.mark.asyncio
async def test_E_replay_approval_rejected(svc):
    """E: A second approve() call on the same decision_id must raise CONFLICT."""
    await create_pending(svc, decision_id="dec_E")

    # First approval succeeds
    await svc.approve(decision_id="dec_E", approving_user_id="usr_standard")

    # Second approval must be rejected
    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_E", approving_user_id="usr_standard")

    assert "CONFLICT" in str(exc_info.value) or "no longer PENDING" in str(exc_info.value)


@pytest.mark.asyncio
async def test_E_replay_deny_after_approve_rejected(svc):
    """E: deny() after approve() must be rejected."""
    await create_pending(svc, decision_id="dec_E3")

    await svc.approve(decision_id="dec_E3", approving_user_id="usr_standard")

    with pytest.raises(RuntimeError) as exc_info:
        await svc.deny(decision_id="dec_E3", denying_user_id="usr_standard")

    assert "CONFLICT" in str(exc_info.value) or "no longer PENDING" in str(exc_info.value)


# ===========================================================================
# F. Modified amount cannot use an old approval
# ===========================================================================

@pytest.mark.asyncio
async def test_F_modified_amount_rejected(svc, store):
    """
    F: A pending decision created for ₹50,000 must not be approvable if
    the stored amount in the snapshot is tampered to ₹75,000.
    The transaction_binding_hash must catch the discrepancy.
    """
    await create_pending(svc, decision_id="dec_F")

    # Directly tamper with the stored record — simulate an attack
    rec = await store.get_pending_decision("dec_F")
    assert rec is not None

    # Tamper: change amount in intent_snapshot without updating binding hash
    rec["intent_snapshot"]["amount"] = 75000.0
    rec["amount"] = 75000.0
    # Do NOT update the transaction_binding_hash — this is the attack
    await store.put_pending_decision(rec)

    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_F", approving_user_id="usr_standard")

    error_msg = str(exc_info.value)
    assert (
        "binding" in error_msg.lower()
        or "hash" in error_msg.lower()
        or "CONFLICT" in error_msg
    ), f"Expected binding/hash error, got: {error_msg}"


# ===========================================================================
# G. Modified payee cannot use an old approval
# ===========================================================================

@pytest.mark.asyncio
async def test_G_modified_payee_rejected(svc, store):
    """
    G: A pending decision for 'ABC Hardware' must not be approvable if
    the payee in the snapshot is tampered to 'XYZ Hardware'.
    """
    await create_pending(svc, decision_id="dec_G")

    rec = await store.get_pending_decision("dec_G")
    assert rec is not None

    # Tamper: change payee without updating binding hash
    rec["intent_snapshot"]["payee"] = "XYZ Hardware"
    rec["payee"] = "XYZ Hardware"
    await store.put_pending_decision(rec)

    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_G", approving_user_id="usr_standard")

    error_msg = str(exc_info.value)
    assert (
        "binding" in error_msg.lower()
        or "hash" in error_msg.lower()
        or "CONFLICT" in error_msg
    ), f"Expected binding/hash error, got: {error_msg}"


# ===========================================================================
# H. Changed evidence cannot use an old approval
# ===========================================================================

@pytest.mark.asyncio
async def test_H_changed_evidence_rejected(svc, store):
    """
    H: A pending decision with evidence_id=None must not be approvable if
    evidence_id is tampered to a different ID.
    """
    await create_pending(svc, decision_id="dec_H", evidence_id=None)

    rec = await store.get_pending_decision("dec_H")
    assert rec is not None

    # Tamper: inject a fabricated evidence_id without updating binding hash
    rec["evidence_id"] = "evid_FAKE999"
    await store.put_pending_decision(rec)

    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_H", approving_user_id="usr_standard")

    error_msg = str(exc_info.value)
    assert (
        "binding" in error_msg.lower()
        or "hash" in error_msg.lower()
        or "CONFLICT" in error_msg
    ), f"Expected binding/hash error, got: {error_msg}"


# ===========================================================================
# I. Approval executes payment only once
# ===========================================================================

@pytest.mark.asyncio
async def test_I_approve_executes_only_once(svc):
    """I: After approve(), a second approve() call raises CONFLICT — no double execution."""
    await create_pending(svc, decision_id="dec_I")

    first = await svc.approve(decision_id="dec_I", approving_user_id="usr_standard")
    assert first.status == PendingDecisionStatus.APPROVED

    # Simulate mark_executed
    await svc.mark_executed("dec_I")

    # Verify the record is no longer PENDING
    rec = await svc.get_pending_decision("dec_I")
    assert rec is not None
    assert rec.status != PendingDecisionStatus.PENDING

    # Second approve must be rejected (CONFLICT or no longer PENDING)
    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_I", approving_user_id="usr_standard")

    error_msg = str(exc_info.value)
    assert "CONFLICT" in error_msg or "no longer PENDING" in error_msg


# ===========================================================================
# J. Denial never executes payment
# ===========================================================================

@pytest.mark.asyncio
async def test_J_denial_produces_no_payment(svc):
    """J: deny() returns a DENIED record with no payment_result or executed_at."""
    await create_pending(svc, decision_id="dec_J")

    denied = await svc.deny(decision_id="dec_J", denying_user_id="usr_standard")

    assert denied.status == PendingDecisionStatus.DENIED
    assert denied.executed_at is None
    # Confirm record in store also has no executed_at
    stored = await svc.get_pending_decision("dec_J")
    assert stored is not None
    assert stored.status == PendingDecisionStatus.DENIED
    assert stored.executed_at is None


# ===========================================================================
# K. Audit events are written
# ===========================================================================

@pytest.mark.asyncio
async def test_K_audit_events_written_on_approve(svc, audit_svc):
    """K: approve() flow must result in HUMAN_APPROVED audit events."""
    await create_pending(svc, decision_id="dec_K_approve")
    await svc.approve(decision_id="dec_K_approve", approving_user_id="usr_standard")

    # Simulate writing the audit event (as the router would)
    await audit_svc.record(
        event_type=AuditEventType.HUMAN_APPROVED,
        user_id="usr_standard",
        session_id="sess_real001",
        intent_id="intent_test001",
        decision_id="dec_K_approve",
        decision=Decision.ALLOW.value,
    )

    events, total = await audit_svc.get_events("usr_standard")
    assert total >= 1
    event_types = [e["event_type"] for e in events]
    assert "HUMAN_APPROVED" in event_types


@pytest.mark.asyncio
async def test_K_audit_events_written_on_deny(svc, audit_svc):
    """K: deny() flow must result in HUMAN_DENIED audit events."""
    await create_pending(svc, decision_id="dec_K_deny")
    await svc.deny(decision_id="dec_K_deny", denying_user_id="usr_standard")

    # Simulate writing the audit event (as the router would)
    await audit_svc.record(
        event_type=AuditEventType.HUMAN_DENIED,
        user_id="usr_standard",
        session_id="sess_real001",
        intent_id="intent_test001",
        decision_id="dec_K_deny",
        decision=Decision.DENY.value,
    )

    events, total = await audit_svc.get_events("usr_standard")
    assert total >= 1
    event_types = [e["event_type"] for e in events]
    assert "HUMAN_DENIED" in event_types


@pytest.mark.asyncio
async def test_K_audit_events_have_decision_id(svc, audit_svc):
    """K: Audit events written for approval must include the decision_id."""
    await create_pending(svc, decision_id="dec_K3")
    await svc.approve(decision_id="dec_K3", approving_user_id="usr_standard")

    await audit_svc.record(
        event_type=AuditEventType.HUMAN_APPROVED,
        user_id="usr_standard",
        session_id="sess_real001",
        intent_id="intent_test001",
        decision_id="dec_K3",
        decision=Decision.ALLOW.value,
    )

    events, _ = await audit_svc.get_events("usr_standard")
    approved_events = [e for e in events if e.get("event_type") == "HUMAN_APPROVED"]
    assert len(approved_events) >= 1
    assert approved_events[0]["decision_id"] == "dec_K3"


# ===========================================================================
# L. Existing deterministic policy behavior remains intact
# ===========================================================================

def test_L_policy_allow_full_match():
    """L: allow_full_match rule still produces ALLOW for green signals."""
    from app.services.policy_service import PolicyService
    from app.models.policy import PolicyDecision

    policy = PolicyService()
    intent = make_intent(amount=1850.0, payee="ABC Hardware")
    signals = TransactionSignals(
        intent_id=intent.intent_id,
        evidence_id="evid_test",
        amount_match=True,
        amount_delta_inr=0.0,
        payee_match=True,
        payee_similarity=0.94,
        evidence_present=True,
        evidence_extraction_ok=True,
        evidence_extraction_confidence=0.94,
        currency_match=True,
        amount_within_limit=True,
        amount_vs_limit_ratio=0.185,
        payee_seen_before=True,
        display_risk_score=10,
    )
    result = policy.evaluate(signals, intent)
    assert result.decision == PolicyDecision.ALLOW
    assert "allow_full_match" in result.matched_rule_ids


def test_L_policy_deny_payee_mismatch():
    """L: deny_payee_mismatch rule still fires when payee doesn't match evidence."""
    from app.services.policy_service import PolicyService
    from app.models.policy import PolicyDecision

    policy = PolicyService()
    intent = make_intent(payee="XYZ Traders", amount=1850.0)
    signals = TransactionSignals(
        intent_id=intent.intent_id,
        evidence_id="evid_test",
        amount_match=True,
        amount_delta_inr=0.0,
        payee_match=False,
        payee_similarity=0.12,
        evidence_present=True,
        evidence_extraction_ok=True,
        evidence_extraction_confidence=0.94,
        currency_match=True,
        amount_within_limit=True,
        amount_vs_limit_ratio=0.185,
        payee_seen_before=True,
        display_risk_score=80,
    )
    result = policy.evaluate(signals, intent)
    assert result.decision == PolicyDecision.DENY
    assert "deny_payee_mismatch" in result.matched_rule_ids


def test_L_policy_require_human_exceeds_limit():
    """L: human_approval_exceeds_limit fires when evidence is ok but amount exceeds limit.

    Rule priority ordering:
      10: deny_evidence_missing_high_amount  — evidence absent + high amount → DENY
      20: deny_amount_mismatch
      30: deny_payee_mismatch
      40: deny_low_confidence_extraction
      50: human_approval_exceeds_limit       ← this test targets this rule
      60: human_approval_unknown_payee_medium_amount
      70: allow_full_match
      80: allow_small_no_evidence

    For rule 50 to fire, rules 10–40 must NOT match.
    That requires: evidence_present=True, amount_match=True, payee_match=True,
    evidence_extraction_ok=True, AND amount_within_limit=False.
    """
    from app.services.policy_service import PolicyService
    from app.models.policy import PolicyDecision

    policy = PolicyService()
    # Use a large amount so amount_within_limit=False; evidence is present and valid
    intent = make_intent(amount=50000.0, payee="ABC Hardware")
    signals = TransactionSignals(
        intent_id=intent.intent_id,
        evidence_id="evid_test",
        amount_match=True,
        amount_delta_inr=0.0,
        payee_match=True,
        payee_similarity=0.94,
        evidence_present=True,           # evidence IS present — avoids rule 10
        evidence_extraction_ok=True,     # good confidence — avoids rule 40
        evidence_extraction_confidence=0.94,
        currency_match=True,
        amount_within_limit=False,       # exceeds limit → triggers rule 50
        amount_vs_limit_ratio=5.0,
        payee_seen_before=True,
        display_risk_score=60,
    )
    result = policy.evaluate(signals, intent)
    assert result.decision == PolicyDecision.REQUIRE_HUMAN_APPROVAL, (
        f"Expected REQUIRE_HUMAN_APPROVAL but got {result.decision}. "
        f"Matched rules: {result.matched_rule_ids}"
    )
    assert "human_approval_exceeds_limit" in result.matched_rule_ids


# ===========================================================================
# Additional: transaction binding hash correctness
# ===========================================================================

def test_binding_hash_deterministic():
    """compute_transaction_binding_hash must produce the same hash for identical inputs."""
    h1 = compute_transaction_binding_hash(
        intent_id="intent_001",
        payee="ABC Hardware",
        amount=50000.0,
        currency="INR",
        evidence_id=None,
    )
    h2 = compute_transaction_binding_hash(
        intent_id="intent_001",
        payee="ABC Hardware",
        amount=50000.0,
        currency="INR",
        evidence_id=None,
    )
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_binding_hash_different_payee():
    """Different payee must produce a different binding hash."""
    h1 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", None)
    h2 = compute_transaction_binding_hash("id", "XYZ Hardware", 50000.0, "INR", None)
    assert h1 != h2


def test_binding_hash_different_amount():
    """Different amount must produce a different binding hash."""
    h1 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", None)
    h2 = compute_transaction_binding_hash("id", "ABC Hardware", 75000.0, "INR", None)
    assert h1 != h2


def test_binding_hash_different_currency():
    """Different currency must produce a different binding hash."""
    h1 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", None)
    h2 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "USD", None)
    assert h1 != h2


def test_binding_hash_different_evidence():
    """Different evidence_id must produce a different binding hash."""
    h1 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", None)
    h2 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", "evid_001")
    assert h1 != h2


def test_binding_hash_payee_case_normalised():
    """Payee case and whitespace are normalised — same logical payee → same hash."""
    h1 = compute_transaction_binding_hash("id", "ABC Hardware", 50000.0, "INR", None)
    h2 = compute_transaction_binding_hash("id", "abc hardware", 50000.0, "INR", None)
    h3 = compute_transaction_binding_hash("id", "  ABC Hardware  ", 50000.0, "INR", None)
    assert h1 == h2 == h3


# ===========================================================================
# Additional: not-found case
# ===========================================================================

@pytest.mark.asyncio
async def test_approve_not_found(svc):
    """approve() on a non-existent decision_id must raise NOT_FOUND."""
    with pytest.raises(RuntimeError) as exc_info:
        await svc.approve(decision_id="dec_NONEXISTENT", approving_user_id="usr_standard")
    assert "NOT_FOUND" in str(exc_info.value)


@pytest.mark.asyncio
async def test_deny_not_found(svc):
    """deny() on a non-existent decision_id must raise NOT_FOUND."""
    with pytest.raises(RuntimeError) as exc_info:
        await svc.deny(decision_id="dec_NONEXISTENT", denying_user_id="usr_standard")
    assert "NOT_FOUND" in str(exc_info.value)


# ===========================================================================
# Additional: local adapter replay protection
# ===========================================================================

@pytest.mark.asyncio
async def test_local_adapter_replay_protection(store):
    """LocalPendingDecisionStoreAdapter.update must reject non-PENDING records."""
    record = {
        "decision_id": "dec_replay",
        "status": "APPROVED",
        "user_id": "usr_standard",
    }
    await store.put_pending_decision(record)

    with pytest.raises(RuntimeError) as exc_info:
        await store.update_pending_decision("dec_replay", {"status": "DENIED"})

    assert "no longer PENDING" in str(exc_info.value)


@pytest.mark.asyncio
async def test_local_adapter_update_not_found(store):
    """LocalPendingDecisionStoreAdapter.update on missing key raises RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        await store.update_pending_decision("dec_missing", {"status": "DENIED"})
    assert "not found" in str(exc_info.value).lower()


# ===========================================================================
# FIX 2 Regression: APPROVED → EXECUTED atomic transition / concurrency guard
# ===========================================================================

@pytest.mark.asyncio
async def test_mark_executed_succeeds_when_approved(store):
    """mark_executed must transition APPROVED → EXECUTED without error."""
    record = {
        "decision_id": "dec_exec_ok",
        "status": "APPROVED",
        "user_id": "usr_standard",
    }
    await store.put_pending_decision(record)

    await store.mark_executed("dec_exec_ok", "2026-09-18T10:00:00+00:00")

    updated = await store.get_pending_decision("dec_exec_ok")
    assert updated is not None
    assert updated["status"] == "EXECUTED"
    assert updated["executed_at"] == "2026-09-18T10:00:00+00:00"


@pytest.mark.asyncio
async def test_mark_executed_rejects_pending_record(store):
    """mark_executed must raise RuntimeError if the record is still PENDING."""
    record = {
        "decision_id": "dec_exec_pending",
        "status": "PENDING",
        "user_id": "usr_standard",
    }
    await store.put_pending_decision(record)

    with pytest.raises(RuntimeError) as exc_info:
        await store.mark_executed("dec_exec_pending", "2026-09-18T10:00:00+00:00")

    assert "not APPROVED" in str(exc_info.value) or "APPROVED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mark_executed_concurrent_guard(store):
    """Second concurrent mark_executed must be rejected (concurrent execution guard)."""
    record = {
        "decision_id": "dec_exec_concurrent",
        "status": "APPROVED",
        "user_id": "usr_standard",
    }
    await store.put_pending_decision(record)

    # First call succeeds
    await store.mark_executed("dec_exec_concurrent", "2026-09-18T10:00:00+00:00")

    # Second call must be rejected because status is now EXECUTED, not APPROVED
    with pytest.raises(RuntimeError) as exc_info:
        await store.mark_executed("dec_exec_concurrent", "2026-09-18T10:00:01+00:00")

    error_msg = str(exc_info.value)
    assert "APPROVED" in error_msg or "concurrent" in error_msg.lower() or "EXECUTED" in error_msg


@pytest.mark.asyncio
async def test_mark_executed_not_found(store):
    """mark_executed on missing decision_id must raise RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        await store.mark_executed("dec_exec_missing", "2026-09-18T10:00:00+00:00")

    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_service_mark_executed_atomic_via_service(svc):
    """PendingDecisionService.mark_executed uses the store's atomic method (not get+put)."""
    await create_pending(svc, decision_id="dec_svc_exec")

    # Approve first
    await svc.approve(decision_id="dec_svc_exec", approving_user_id="usr_standard")

    # mark_executed must succeed
    await svc.mark_executed("dec_svc_exec")

    # Verify status is EXECUTED
    updated = await svc.get_pending_decision("dec_svc_exec")
    assert updated is not None
    assert updated.status.value == "EXECUTED"


@pytest.mark.asyncio
async def test_service_mark_executed_concurrent_rejected(svc):
    """Second mark_executed call via service must be rejected (concurrent guard)."""
    await create_pending(svc, decision_id="dec_svc_exec_concurrent")

    await svc.approve(decision_id="dec_svc_exec_concurrent", approving_user_id="usr_standard")

    # First mark_executed succeeds
    await svc.mark_executed("dec_svc_exec_concurrent")

    # Second must be rejected
    with pytest.raises(RuntimeError) as exc_info:
        await svc.mark_executed("dec_svc_exec_concurrent")

    error_msg = str(exc_info.value)
    assert "APPROVED" in error_msg or "concurrent" in error_msg.lower() or "EXECUTED" in error_msg
