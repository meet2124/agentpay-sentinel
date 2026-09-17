"""
AgentPay Sentinel — Integration Tests: Full Workflow

All 10 mandatory test scenarios exercised via the FastAPI test client.
No real AWS/Bedrock calls — uses local adapters and JSON fixtures.
"""

import json
import os
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.authorization import Decision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
INVOICE_FILE = FIXTURE_DIR / "sample_invoice.json"


@pytest.fixture(scope="module")
def client():
    """Shared test client across all tests in this module."""
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_token(client):
    """Obtain a valid bearer token for usr_standard."""
    resp = client.post("/auth/session", json={
        "user_id": "usr_standard",
        "api_key": "sk-dev-standard",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def evidence_id(client, auth_headers):
    """Upload the sample invoice once; return its evidence_id."""
    with open(INVOICE_FILE, "rb") as f:
        resp = client.post(
            "/evidence/upload",
            files={"file": ("invoice_abc_hardware.json", f, "application/json")},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["evidence_id"]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["sandbox_only"] is True


# ---------------------------------------------------------------------------
# TEST 1 — HAPPY PATH: matching intent + matching evidence → ALLOW
# ---------------------------------------------------------------------------

def test_01_happy_path_allow(client, auth_headers, evidence_id):
    """
    Intent: ₹1,850 → ABC Hardware
    Evidence: ₹1,850 → ABC Hardware Co. (INV-042)
    Expected: ALLOW + SIMULATED_SUCCESS
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to ABC Hardware.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.ALLOW.value
    assert decision["payment_result"] is not None
    assert decision["payment_result"]["status"] == "SIMULATED_SUCCESS"
    assert "MOCK-" in decision["payment_result"]["transaction_id"]
    assert "sandbox" in decision["payment_result"]["disclaimer"].lower()
    assert data["audit_event_id"] != "unknown"


# ---------------------------------------------------------------------------
# TEST 2 — KILLER DENIAL: amount AND payee both wrong
# ---------------------------------------------------------------------------

def test_02_killer_denial_amount_and_payee_mismatch(client, auth_headers, evidence_id):
    """
    Evidence: ₹1,850 → ABC Hardware
    Agent action: ₹18,500 → XYZ Traders

    Expected:
      amount_match = FALSE
      payee_match  = FALSE
      decision     = DENY
      No mock payment
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹18500 to XYZ Traders.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.DENY.value
    assert decision["payment_result"] is None
    assert decision["signals"]["amount_match"] is False
    assert decision["signals"]["payee_match"] is False
    assert "deny" in decision["matched_rule_ids"][0]


# ---------------------------------------------------------------------------
# TEST 3 — AMOUNT MISMATCH ONLY
# ---------------------------------------------------------------------------

def test_03_amount_mismatch_deny(client, auth_headers, evidence_id):
    """
    Intent: ₹5,000 → ABC Hardware (correct payee, wrong amount)
    Evidence: ₹1,850 → ABC Hardware Co.
    Expected: DENY (amount mismatch rule)
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹5000 to ABC Hardware.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.DENY.value
    assert decision["signals"]["amount_match"] is False
    assert decision["signals"]["payee_match"] is True
    assert decision["payment_result"] is None
    assert "deny_amount_mismatch" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 4 — PAYEE MISMATCH ONLY
# ---------------------------------------------------------------------------

def test_04_payee_mismatch_deny(client, auth_headers, evidence_id):
    """
    Intent: ₹1,850 → XYZ Traders (wrong payee, correct amount)
    Evidence: ₹1,850 → ABC Hardware Co.
    Expected: DENY (payee mismatch rule)
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to XYZ Traders.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.DENY.value
    assert decision["signals"]["amount_match"] is True
    assert decision["signals"]["payee_match"] is False
    assert decision["payment_result"] is None
    assert "deny_payee_mismatch" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 5 — SPENDING LIMIT EXCEEDED → REQUIRE_HUMAN_APPROVAL
# ---------------------------------------------------------------------------

def test_05_exceeds_spending_limit(client, auth_headers):
    """
    Use usr_basic (₹1,000 limit). Request ₹5,000 with matching evidence.
    Expected: REQUIRE_HUMAN_APPROVAL — no payment.
    """
    # Get token for basic user (₹1,000 limit)
    basic_resp = client.post("/auth/session", json={
        "user_id": "usr_basic",
        "api_key": "sk-dev-basic",
    })
    assert basic_resp.status_code == 200
    basic_token = basic_resp.json()["token"]
    basic_headers = {"Authorization": f"Bearer {basic_token}"}

    # Upload evidence for basic user
    with open(INVOICE_FILE, "rb") as f:
        ev_resp = client.post(
            "/evidence/upload",
            files={"file": ("invoice.json", f, "application/json")},
            headers=basic_headers,
        )
    assert ev_resp.status_code == 200
    ev_id = ev_resp.json()["evidence_id"]

    # The invoice is for ₹1,850 which exceeds the ₹1,000 limit
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to ABC Hardware.",
        "evidence_id": ev_id,
    }, headers=basic_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.REQUIRE_HUMAN_APPROVAL.value
    assert decision["payment_result"] is None
    assert decision["requires_human"] is True
    assert "human_approval_exceeds_limit" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 6 — MISSING EVIDENCE, HIGH AMOUNT → DENY
# ---------------------------------------------------------------------------

def test_06_missing_evidence_high_amount(client, auth_headers):
    """
    No evidence uploaded. Amount = ₹2,000 (> ₹500 threshold).
    Expected: DENY (no evidence, high amount rule).
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹2000 to ABC Hardware.",
        # No evidence_id
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.DENY.value
    assert decision["signals"]["evidence_present"] is False
    assert decision["payment_result"] is None
    assert "deny_evidence_missing_high_amount" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 7 — LOW CONFIDENCE EXTRACTION → DENY
# ---------------------------------------------------------------------------

def test_07_low_confidence_extraction_deny(client, auth_headers):
    """
    Upload evidence JSON with extraction_confidence=0.40 (< 0.70 threshold).
    Expected: DENY (low confidence extraction rule).
    """
    low_confidence_invoice = {
        "vendor_name": "ABC Hardware Co.",
        "amount": 1850.0,
        "currency": "INR",
        "invoice_number": "INV-042",
        "extraction_confidence": 0.40,  # below threshold
        "extraction_method": "STUB",
    }
    ev_resp = client.post(
        "/evidence/upload",
        files={"file": ("low_conf.json", json.dumps(low_confidence_invoice).encode(), "application/json")},
        headers=auth_headers,
    )
    assert ev_resp.status_code == 200
    ev_id = ev_resp.json()["evidence_id"]

    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to ABC Hardware.",
        "evidence_id": ev_id,
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.DENY.value
    assert decision["signals"]["evidence_extraction_ok"] is False
    assert decision["payment_result"] is None
    assert "deny_low_confidence_extraction" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 8 — SMALL PAYMENT, NO EVIDENCE → ALLOW
# ---------------------------------------------------------------------------

def test_08_small_payment_no_evidence_allow(client, auth_headers):
    """
    Amount = ₹300 (< ₹500 threshold). No evidence. Within spending limit.
    Expected: ALLOW + SIMULATED_SUCCESS
    """
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹300 to Tea Stall.",
        # No evidence_id
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    decision = data["authorization"]

    assert decision["decision"] == Decision.ALLOW.value
    assert decision["payment_result"] is not None
    assert decision["payment_result"]["status"] == "SIMULATED_SUCCESS"
    assert "allow_small_no_evidence" in decision["matched_rule_ids"]


# ---------------------------------------------------------------------------
# TEST 9 — AUDIT TAMPERING (Integration: verify endpoint)
# ---------------------------------------------------------------------------

def test_09_audit_chain_integrity_after_valid_workflow(client, auth_headers, evidence_id):
    """
    After running a valid workflow, the hash chain must verify cleanly.
    """
    # Run a payment to generate audit events
    client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to ABC Hardware.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)

    resp = client.get("/audit/verify", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["chain_valid"] is True
    assert data["events_checked"] >= 1
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# TEST 10 — FRONTEND BYPASS PROTECTION
# ---------------------------------------------------------------------------

def test_10_payment_simulator_refuses_non_allow_decisions(client, auth_headers, evidence_id):
    """
    Attempt to call evaluate where the decision would be DENY,
    and verify the payment_result is always None — simulator never fires.
    """
    # Payee mismatch → DENY
    resp = client.post("/payments/evaluate", json={
        "raw_input": "Pay ₹1850 to Totally Different Company.",
        "evidence_id": evidence_id,
    }, headers=auth_headers)
    assert resp.status_code == 200
    decision = resp.json()["authorization"]

    # Payment simulator must have refused
    assert decision["payment_result"] is None
    assert decision["decision"] in [Decision.DENY.value, Decision.REQUIRE_HUMAN_APPROVAL.value]


def test_10b_payment_simulator_unit_level_refuses_deny():
    """
    Direct unit test of payment simulator — must raise 403 for DENY decision.
    """
    import asyncio
    from app.models.authorization import Decision
    from app.models.payment_intent import PaymentIntent
    from app.services.payment_simulator import PaymentSimulator
    from fastapi import HTTPException

    simulator = PaymentSimulator()

    intent = PaymentIntent(
        intent_id="intent_x",
        user_id="usr_test",
        session_id="sess_x",
        raw_input="Pay ₹1850 to ABC Hardware.",
        payee="ABC Hardware",
        amount=1850.0,
        currency="INR",
        confidence_score=0.95,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            simulator.simulate(final_decision=Decision.DENY, intent=intent)
        )
    assert exc_info.value.status_code == 403


def test_10c_payment_simulator_unit_level_refuses_hra():
    """Payment simulator must raise 403 for REQUIRE_HUMAN_APPROVAL."""
    import asyncio
    from app.models.authorization import Decision
    from app.models.payment_intent import PaymentIntent
    from app.services.payment_simulator import PaymentSimulator
    from fastapi import HTTPException

    simulator = PaymentSimulator()
    intent = PaymentIntent(
        intent_id="intent_y",
        user_id="usr_test",
        session_id="sess_y",
        raw_input="Pay ₹1850 to ABC Hardware.",
        payee="ABC Hardware",
        amount=1850.0,
        currency="INR",
        confidence_score=0.95,
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            simulator.simulate(
                final_decision=Decision.REQUIRE_HUMAN_APPROVAL, intent=intent
            )
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Additional: Input validation
# ---------------------------------------------------------------------------

def test_validation_empty_raw_input(client, auth_headers):
    resp = client.post("/payments/evaluate", json={
        "raw_input": "",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_validation_missing_raw_input(client, auth_headers):
    resp = client.post("/payments/evaluate", json={}, headers=auth_headers)
    assert resp.status_code == 422


def test_auth_required(client):
    resp = client.post("/payments/evaluate", json={"raw_input": "Pay ₹100 to X."})
    assert resp.status_code == 401


def test_invalid_token(client):
    resp = client.get("/audit/events", headers={"Authorization": "Bearer invalid_token_xyz"})
    assert resp.status_code == 401
