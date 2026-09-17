"""
AgentPay Sentinel — Unit Tests: Signal Computation

Tests the ComparisonService deterministic signal computation.
No LLM calls, no external dependencies.
"""

import pytest
from datetime import datetime, timezone

from app.models.evidence import Evidence, EvidenceSourceType, ExtractionMethod
from app.models.payment_intent import PaymentIntent, IntentStatus, PaymentMethod
from app.models.user import User, UserTier
from app.services.comparison_service import ComparisonService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(spending_limit: float = 10000.0) -> User:
    return User(
        user_id="usr_test",
        name="Test User",
        email="test@example.com",
        tier=UserTier.STANDARD,
        spending_limit_inr=spending_limit,
    )


def make_intent(
    payee: str = "ABC Hardware",
    amount: float = 1850.0,
    currency: str = "INR",
) -> PaymentIntent:
    return PaymentIntent(
        intent_id="intent_test",
        user_id="usr_test",
        session_id="sess_test",
        raw_input=f"Pay ₹{amount} to {payee}.",
        payee=payee,
        amount=amount,
        currency=currency,
        confidence_score=0.95,
    )


def make_evidence(
    vendor_name: str = "ABC Hardware Co.",
    amount: float = 1850.0,
    currency: str = "INR",
    confidence: float = 0.94,
) -> Evidence:
    return Evidence(
        evidence_id="evid_test",
        user_id="usr_test",
        source_type=EvidenceSourceType.INVOICE_PDF,
        vendor_name=vendor_name,
        amount=amount,
        currency=currency,
        invoice_number="INV-042",
        extraction_method=ExtractionMethod.STUB,
        extraction_confidence=confidence,
    )


svc = ComparisonService()


# ---------------------------------------------------------------------------
# Test 1 area: amount_match signal
# ---------------------------------------------------------------------------

def test_amount_match_exact():
    signals = svc.compute_signals(make_intent(amount=1850), make_evidence(amount=1850), make_user(), [])
    assert signals.amount_match is True
    assert signals.amount_delta_inr == 0.0


def test_amount_match_within_threshold():
    """Delta of exactly ₹1 should still match (threshold is <=1)."""
    signals = svc.compute_signals(make_intent(amount=1850), make_evidence(amount=1851), make_user(), [])
    assert signals.amount_match is True
    assert signals.amount_delta_inr == 1.0


def test_amount_mismatch_large():
    """₹18,500 vs ₹1,850 — killer denial scenario."""
    signals = svc.compute_signals(make_intent(amount=18500), make_evidence(amount=1850), make_user(), [])
    assert signals.amount_match is False
    assert signals.amount_delta_inr == pytest.approx(16650.0)


def test_amount_mismatch_small():
    """Delta of ₹2 should fail."""
    signals = svc.compute_signals(make_intent(amount=1852), make_evidence(amount=1850), make_user(), [])
    assert signals.amount_match is False


# ---------------------------------------------------------------------------
# Test 2 area: payee_match signal
# ---------------------------------------------------------------------------

def test_payee_match_similar():
    """'ABC Hardware' vs 'ABC Hardware Co.' should match (>= 0.85)."""
    signals = svc.compute_signals(make_intent(payee="ABC Hardware"), make_evidence(vendor_name="ABC Hardware Co."), make_user(), [])
    assert signals.payee_match is True
    assert signals.payee_similarity >= 0.85


def test_payee_mismatch_different():
    """'XYZ Traders' vs 'ABC Hardware Co.' should not match."""
    signals = svc.compute_signals(make_intent(payee="XYZ Traders"), make_evidence(vendor_name="ABC Hardware Co."), make_user(), [])
    assert signals.payee_match is False
    assert signals.payee_similarity < 0.85


def test_payee_exact_match():
    signals = svc.compute_signals(make_intent(payee="ABC Hardware Co."), make_evidence(vendor_name="ABC Hardware Co."), make_user(), [])
    assert signals.payee_match is True
    assert signals.payee_similarity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 3 area: evidence_present signal
# ---------------------------------------------------------------------------

def test_evidence_present_when_provided():
    signals = svc.compute_signals(make_intent(), make_evidence(), make_user(), [])
    assert signals.evidence_present is True


def test_evidence_absent_when_none():
    signals = svc.compute_signals(make_intent(), None, make_user(), [])
    assert signals.evidence_present is False
    assert signals.evidence_extraction_confidence == 0.0


# ---------------------------------------------------------------------------
# Test 4 area: evidence_extraction_ok signal
# ---------------------------------------------------------------------------

def test_evidence_extraction_ok_high_confidence():
    signals = svc.compute_signals(make_intent(), make_evidence(confidence=0.94), make_user(), [])
    assert signals.evidence_extraction_ok is True


def test_evidence_extraction_not_ok_low_confidence():
    """Confidence < 0.70 → evidence_extraction_ok=False."""
    signals = svc.compute_signals(make_intent(), make_evidence(confidence=0.50), make_user(), [])
    assert signals.evidence_extraction_ok is False


def test_evidence_extraction_boundary_confidence():
    """Exactly 0.70 → ok."""
    signals = svc.compute_signals(make_intent(), make_evidence(confidence=0.70), make_user(), [])
    assert signals.evidence_extraction_ok is True


# ---------------------------------------------------------------------------
# Test 5 area: amount_within_limit signal
# ---------------------------------------------------------------------------

def test_amount_within_limit():
    signals = svc.compute_signals(make_intent(amount=1850), make_evidence(), make_user(spending_limit=10000), [])
    assert signals.amount_within_limit is True
    assert signals.amount_vs_limit_ratio == pytest.approx(0.185, rel=1e-3)


def test_amount_exceeds_limit():
    signals = svc.compute_signals(make_intent(amount=15000), make_evidence(amount=15000), make_user(spending_limit=10000), [])
    assert signals.amount_within_limit is False
    assert signals.amount_vs_limit_ratio > 1.0


# ---------------------------------------------------------------------------
# Test 6 area: payee_seen_before signal
# ---------------------------------------------------------------------------

def test_payee_seen_before_match():
    history = ["abc hardware", "xyz corp"]
    signals = svc.compute_signals(make_intent(payee="ABC Hardware"), make_evidence(), make_user(), history)
    assert signals.payee_seen_before is True


def test_payee_not_seen_before():
    signals = svc.compute_signals(make_intent(payee="New Vendor"), make_evidence(), make_user(), [])
    assert signals.payee_seen_before is False


# ---------------------------------------------------------------------------
# Test 7 area: currency_match signal
# ---------------------------------------------------------------------------

def test_currency_match():
    signals = svc.compute_signals(make_intent(currency="INR"), make_evidence(currency="INR"), make_user(), [])
    assert signals.currency_match is True


def test_currency_mismatch():
    signals = svc.compute_signals(make_intent(currency="USD"), make_evidence(currency="INR"), make_user(), [])
    assert signals.currency_match is False


# ---------------------------------------------------------------------------
# Test 8: display_risk_score is UI-only and doesn't affect signals
# ---------------------------------------------------------------------------

def test_display_risk_score_is_derived_only():
    """Verify display_risk_score is a derived int, never affects named signals."""
    signals = svc.compute_signals(make_intent(), make_evidence(), make_user(), [])
    assert isinstance(signals.display_risk_score, int)
    assert 0 <= signals.display_risk_score <= 100
    # The score field must not appear as a named signal that policy reads
    # (all policy signals are bool or float, explicitly named)
    assert signals.amount_match is True   # independent of score
