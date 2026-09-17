"""
AgentPay Sentinel — Unit Tests: Policy Engine

Tests each of the 8 policy rules: matching case + non-matching case.
Covers all mandatory test cases for policy decisions.
"""

import pytest
from datetime import datetime, timezone

from app.models.payment_intent import PaymentIntent, IntentStatus
from app.models.policy import PolicyDecision
from app.models.signals import TransactionSignals
from app.models.user import User, UserTier
from app.services.policy_service import PolicyService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_intent(payee: str = "ABC Hardware", amount: float = 1850.0) -> PaymentIntent:
    return PaymentIntent(
        intent_id="intent_test",
        user_id="usr_test",
        session_id="sess_test",
        raw_input=f"Pay ₹{amount} to {payee}.",
        payee=payee,
        amount=amount,
        currency="INR",
        confidence_score=0.95,
    )


def make_signals(
    *,
    amount_match: bool = True,
    amount_delta_inr: float = 0.0,
    payee_match: bool = True,
    payee_similarity: float = 0.94,
    evidence_present: bool = True,
    evidence_extraction_ok: bool = True,
    evidence_extraction_confidence: float = 0.94,
    currency_match: bool = True,
    amount_within_limit: bool = True,
    amount_vs_limit_ratio: float = 0.185,
    payee_seen_before: bool = True,
    display_risk_score: int = 10,
) -> TransactionSignals:
    return TransactionSignals(
        intent_id="intent_test",
        evidence_id="evid_test",
        amount_match=amount_match,
        amount_delta_inr=amount_delta_inr,
        payee_match=payee_match,
        payee_similarity=payee_similarity,
        evidence_present=evidence_present,
        evidence_extraction_ok=evidence_extraction_ok,
        evidence_extraction_confidence=evidence_extraction_confidence,
        currency_match=currency_match,
        amount_within_limit=amount_within_limit,
        amount_vs_limit_ratio=amount_vs_limit_ratio,
        payee_seen_before=payee_seen_before,
        display_risk_score=display_risk_score,
    )


policy = PolicyService()


# ---------------------------------------------------------------------------
# Rule 10: deny_evidence_missing_high_amount
# ---------------------------------------------------------------------------

def test_rule10_deny_no_evidence_high_amount():
    """Amount > ₹500, no evidence → DENY."""
    signals = make_signals(evidence_present=False)
    result = policy.evaluate(signals, make_intent(amount=1850))
    assert result.decision == PolicyDecision.DENY
    assert "deny_evidence_missing_high_amount" in result.matched_rule_ids


def test_rule10_allow_small_no_evidence_skips_rule10():
    """Amount <= ₹500, no evidence → should NOT trigger rule 10."""
    signals = make_signals(evidence_present=False)
    result = policy.evaluate(signals, make_intent(amount=300))
    # Should reach rule 80 (allow_small_no_evidence), not rule 10
    assert "deny_evidence_missing_high_amount" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 20: deny_amount_mismatch
# ---------------------------------------------------------------------------

def test_rule20_deny_amount_mismatch():
    """Evidence present, amount doesn't match → DENY."""
    signals = make_signals(amount_match=False, amount_delta_inr=16650.0)
    result = policy.evaluate(signals, make_intent(amount=18500))
    assert result.decision == PolicyDecision.DENY
    assert "deny_amount_mismatch" in result.matched_rule_ids


def test_rule20_does_not_fire_on_match():
    signals = make_signals(amount_match=True)
    result = policy.evaluate(signals, make_intent())
    assert "deny_amount_mismatch" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 30: deny_payee_mismatch
# ---------------------------------------------------------------------------

def test_rule30_deny_payee_mismatch():
    """Evidence present, payee doesn't match → DENY."""
    signals = make_signals(payee_match=False, payee_similarity=0.12)
    result = policy.evaluate(signals, make_intent(payee="XYZ Traders"))
    assert result.decision == PolicyDecision.DENY
    assert "deny_payee_mismatch" in result.matched_rule_ids


def test_rule30_does_not_fire_on_match():
    signals = make_signals(payee_match=True, payee_similarity=0.94)
    result = policy.evaluate(signals, make_intent())
    assert "deny_payee_mismatch" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 40: deny_low_confidence_extraction
# ---------------------------------------------------------------------------

def test_rule40_deny_low_confidence():
    """Evidence present, low extraction confidence → DENY."""
    signals = make_signals(
        evidence_extraction_ok=False,
        evidence_extraction_confidence=0.50,
    )
    result = policy.evaluate(signals, make_intent())
    assert result.decision == PolicyDecision.DENY
    assert "deny_low_confidence_extraction" in result.matched_rule_ids


def test_rule40_does_not_fire_on_ok_confidence():
    signals = make_signals(evidence_extraction_ok=True, evidence_extraction_confidence=0.94)
    result = policy.evaluate(signals, make_intent())
    assert "deny_low_confidence_extraction" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 50: human_approval_exceeds_limit
# ---------------------------------------------------------------------------

def test_rule50_human_approval_exceeds_limit():
    """Amount exceeds spending limit → REQUIRE_HUMAN_APPROVAL."""
    signals = make_signals(amount_within_limit=False, amount_vs_limit_ratio=1.5)
    result = policy.evaluate(signals, make_intent(amount=15000))
    assert result.decision == PolicyDecision.REQUIRE_HUMAN_APPROVAL
    assert "human_approval_exceeds_limit" in result.matched_rule_ids


def test_rule50_does_not_fire_within_limit():
    signals = make_signals(amount_within_limit=True, amount_vs_limit_ratio=0.185)
    result = policy.evaluate(signals, make_intent())
    assert "human_approval_exceeds_limit" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 60: human_approval_unknown_payee_medium_amount
# ---------------------------------------------------------------------------

def test_rule60_human_approval_new_payee_medium_amount():
    """Unknown payee, amount > ₹2,000 → REQUIRE_HUMAN_APPROVAL."""
    signals = make_signals(payee_seen_before=False)
    result = policy.evaluate(signals, make_intent(amount=3000))
    assert result.decision == PolicyDecision.REQUIRE_HUMAN_APPROVAL
    assert "human_approval_unknown_payee_medium_amount" in result.matched_rule_ids


def test_rule60_does_not_fire_known_payee():
    signals = make_signals(payee_seen_before=True)
    result = policy.evaluate(signals, make_intent(amount=3000))
    assert "human_approval_unknown_payee_medium_amount" not in result.matched_rule_ids


def test_rule60_does_not_fire_small_amount():
    """Unknown payee but amount <= ₹2,000 → should NOT trigger rule 60."""
    signals = make_signals(payee_seen_before=False)
    result = policy.evaluate(signals, make_intent(amount=1500))
    assert "human_approval_unknown_payee_medium_amount" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 70: allow_full_match
# ---------------------------------------------------------------------------

def test_rule70_allow_full_match():
    """All signals green → ALLOW."""
    signals = make_signals()  # all defaults are green
    result = policy.evaluate(signals, make_intent())
    assert result.decision == PolicyDecision.ALLOW
    assert "allow_full_match" in result.matched_rule_ids


def test_rule70_does_not_fire_on_mismatch():
    signals = make_signals(amount_match=False)
    result = policy.evaluate(signals, make_intent())
    assert "allow_full_match" not in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Rule 80: allow_small_no_evidence
# ---------------------------------------------------------------------------

def test_rule80_allow_small_no_evidence():
    """Amount <= ₹500, no evidence, within limit → ALLOW."""
    signals = make_signals(
        evidence_present=False,
        evidence_extraction_ok=False,
        evidence_extraction_confidence=0.0,
        amount_match=True,    # vacuously true
        payee_match=True,     # vacuously true
        currency_match=True,
        amount_within_limit=True,
        payee_seen_before=False,
        display_risk_score=30,
    )
    result = policy.evaluate(signals, make_intent(amount=300))
    assert result.decision == PolicyDecision.ALLOW
    assert "allow_small_no_evidence" in result.matched_rule_ids


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

def test_priority_deny_before_human_approval():
    """Amount mismatch (rule 20) should fire before exceeds limit (rule 50)."""
    signals = make_signals(
        amount_match=False,
        amount_delta_inr=200.0,
        amount_within_limit=False,   # both conditions true
    )
    result = policy.evaluate(signals, make_intent(amount=15000))
    # Rule 20 has priority 20, rule 50 has priority 50 → rule 20 wins
    assert result.matched_rule_ids[0] == "deny_amount_mismatch"
    assert result.decision == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Reason strings
# ---------------------------------------------------------------------------

def test_reason_mentions_amounts_on_mismatch():
    signals = make_signals(amount_match=False, amount_delta_inr=16650.0)
    result = policy.evaluate(signals, make_intent(amount=18500))
    assert "mismatch" in result.reason.lower()


def test_reason_mentions_payee_on_mismatch():
    signals = make_signals(payee_match=False, payee_similarity=0.12)
    result = policy.evaluate(signals, make_intent(payee="XYZ Traders"))
    assert "payee" in result.reason.lower() or "xyz" in result.reason.lower()
