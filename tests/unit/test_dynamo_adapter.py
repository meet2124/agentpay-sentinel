"""
AgentPay Sentinel — Unit Tests: DynamoDB Adapters

Uses moto to mock AWS DynamoDB entirely in-process.
No real AWS credentials or real DynamoDB requests are made.

Tests cover:
  DynamoAuditStoreAdapter — put_event, get_events, get_event, get_last_event_hash
  DynamoSessionStoreAdapter — get_user, create/get session, payee history
  DynamoEvidenceStoreAdapter — put_evidence, get_evidence

Audit chain integrity (hash chain correctness) is tested via AuditService
integration in tests/unit/test_audit_chain.py (no change to those tests).
These tests verify the DynamoDB layer independently.

Run: python -m pytest tests/unit/test_dynamo_adapter.py -v
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

# Moto requires fake credentials — set before importing boto3 clients
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

from app.adapters.dynamo import (
    DynamoAuditStoreAdapter,
    DynamoEvidenceStoreAdapter,
    DynamoSessionStoreAdapter,
)
from app.utils.crypto import GENESIS_HASH

_REGION = "ap-south-1"
_AUDIT_TABLE = "test-sentinel-audit"
_SESSIONS_TABLE = "test-sentinel-sessions"


class _AuditSettings:
    DYNAMODB_TABLE_AUDIT = _AUDIT_TABLE
    AWS_REGION = _REGION


class _SessionsSettings:
    DYNAMODB_TABLE_SESSIONS = _SESSIONS_TABLE
    DYNAMODB_TABLE_AUDIT = _AUDIT_TABLE
    AWS_REGION = _REGION
    SESSION_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Fixtures: create moto tables before each test
# ---------------------------------------------------------------------------

def _create_audit_table(ddb):
    ddb.create_table(
        TableName=_AUDIT_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "ts_event_id", "AttributeType": "S"},
            {"AttributeName": "event_id", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "ts_event_id", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "event_id-index",
                "KeySchema": [{"AttributeName": "event_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


def _create_sessions_table(ddb):
    ddb.create_table(
        TableName=_SESSIONS_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )


@pytest.fixture()
def audit_adapter():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        _create_audit_table(ddb)
        yield DynamoAuditStoreAdapter(settings=_AuditSettings())


@pytest.fixture()
def session_adapter():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        _create_sessions_table(ddb)
        yield DynamoSessionStoreAdapter(settings=_SessionsSettings())


@pytest.fixture()
def evidence_adapter():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        _create_sessions_table(ddb)
        yield DynamoEvidenceStoreAdapter(settings=_SessionsSettings())


# ---------------------------------------------------------------------------
# Audit Store Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_genesis_hash_when_empty(audit_adapter):
    """get_last_event_hash must return GENESIS_HASH for a new user."""
    result = await audit_adapter.get_last_event_hash("usr_new")
    assert result == GENESIS_HASH


@pytest.mark.asyncio
async def test_audit_put_and_get_event(audit_adapter):
    """put_event + get_event by event_id must roundtrip correctly."""
    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    event = {
        "event_id": event_id,
        "user_id": "usr_test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "AUTHORIZATION_DECISION",
        "decision": "ALLOW",
        "event_hash": "abc123",
        "chained_hash": "def456",
        "prev_hash": GENESIS_HASH,
    }
    await audit_adapter.put_event(event)

    retrieved = await audit_adapter.get_event(event_id)
    assert retrieved is not None
    assert retrieved["event_id"] == event_id
    assert retrieved["decision"] == "ALLOW"
    # Internal DynamoDB keys must be stripped
    assert "pk" not in retrieved
    assert "ts_event_id" not in retrieved


@pytest.mark.asyncio
async def test_audit_get_event_not_found(audit_adapter):
    """get_event must return None for a non-existent event_id."""
    result = await audit_adapter.get_event("evt_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_audit_get_last_event_hash_after_put(audit_adapter):
    """get_last_event_hash must return the hash of the most recent event."""
    user_id = "usr_hash_test"
    ts1 = "2026-09-17T10:00:00+00:00"
    ts2 = "2026-09-17T11:00:00+00:00"

    await audit_adapter.put_event({
        "event_id": "evt_first",
        "user_id": user_id,
        "timestamp": ts1,
        "event_type": "AUTHORIZATION_DECISION",
        "decision": "DENY",
        "event_hash": "hash_first",
        "chained_hash": "chained_first",
        "prev_hash": GENESIS_HASH,
    })
    await audit_adapter.put_event({
        "event_id": "evt_second",
        "user_id": user_id,
        "timestamp": ts2,
        "event_type": "AUTHORIZATION_DECISION",
        "decision": "ALLOW",
        "event_hash": "hash_second",
        "chained_hash": "chained_second",
        "prev_hash": "chained_first",
    })

    last_hash = await audit_adapter.get_last_event_hash(user_id)
    assert last_hash == "hash_second"


@pytest.mark.asyncio
async def test_audit_get_events_returns_list(audit_adapter):
    """get_events must return (list, total) for a user with events."""
    user_id = "usr_list_test"
    for i in range(3):
        await audit_adapter.put_event({
            "event_id": f"evt_{i}",
            "user_id": user_id,
            "timestamp": f"2026-09-17T0{i}:00:00+00:00",
            "event_type": "AUTHORIZATION_DECISION",
            "decision": "ALLOW",
            "event_hash": f"hash_{i}",
            "chained_hash": f"chained_{i}",
            "prev_hash": GENESIS_HASH,
        })

    events, total = await audit_adapter.get_events(user_id)
    assert total == 3
    assert len(events) == 3
    # Verify internal keys are stripped
    for ev in events:
        assert "pk" not in ev
        assert "ts_event_id" not in ev


@pytest.mark.asyncio
async def test_audit_float_amounts_round_trip(audit_adapter):
    """Float amounts serialised through Decimal must round-trip correctly."""
    event_id = "evt_float"
    await audit_adapter.put_event({
        "event_id": event_id,
        "user_id": "usr_float",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "AUTHORIZATION_DECISION",
        "decision": "ALLOW",
        "event_hash": "h",
        "chained_hash": "ch",
        "prev_hash": GENESIS_HASH,
        "amount": 1850.50,       # float → Decimal → float roundtrip
        "confidence": 0.95,
    })

    retrieved = await audit_adapter.get_event(event_id)
    assert retrieved is not None
    # Float must be preserved (not an integer)
    assert abs(retrieved["amount"] - 1850.50) < 0.01


# ---------------------------------------------------------------------------
# Session Store Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_get_demo_user_fallback(session_adapter):
    """Demo users must be retrievable even if not seeded into DynamoDB."""
    user = await session_adapter.get_user("usr_standard")
    assert user is not None
    assert user["user_id"] == "usr_standard"
    assert user["tier"] == "STANDARD"


@pytest.mark.asyncio
async def test_session_get_user_not_found(session_adapter):
    """Unknown user must return None."""
    user = await session_adapter.get_user("usr_does_not_exist")
    assert user is None


@pytest.mark.asyncio
async def test_session_get_by_api_key_demo(session_adapter):
    """Demo API keys must map to the correct user."""
    user = await session_adapter.get_user_by_api_key("sk-dev-standard")
    assert user is not None
    assert user["user_id"] == "usr_standard"


@pytest.mark.asyncio
async def test_session_create_and_retrieve(session_adapter):
    """Created sessions must be retrievable by token."""
    token = f"tok_{uuid.uuid4().hex}"
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    await session_adapter.create_session(
        user_id="usr_standard",
        session_id=session_id,
        token=token,
        expires_at=expires_at,
    )

    session = await session_adapter.get_session(token)
    assert session is not None
    assert session["user_id"] == "usr_standard"
    assert session["session_id"] == session_id
    assert session["token"] == token


@pytest.mark.asyncio
async def test_session_expired_returns_none(session_adapter):
    """A session with an expired TTL must return None from get_session."""
    token = f"tok_expired_{uuid.uuid4().hex}"
    # Set expiry in the past
    expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    await session_adapter.create_session(
        user_id="usr_standard",
        session_id="sess_expired",
        token=token,
        expires_at=expires_at,
    )

    result = await session_adapter.get_session(token)
    assert result is None


@pytest.mark.asyncio
async def test_session_get_nonexistent_token(session_adapter):
    """Unknown token must return None."""
    result = await session_adapter.get_session("tok_nonexistent_12345")
    assert result is None


@pytest.mark.asyncio
async def test_payee_history_empty_initially(session_adapter):
    """New user must have an empty payee history."""
    history = await session_adapter.get_payee_history("usr_new_payee_test")
    assert history == []


@pytest.mark.asyncio
async def test_payee_record_and_retrieve(session_adapter):
    """record_payee + get_payee_history must be consistent."""
    user_id = "usr_payee_test"
    await session_adapter.record_payee(user_id, "ABC Hardware")
    await session_adapter.record_payee(user_id, "XYZ Traders")

    history = await session_adapter.get_payee_history(user_id)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_payee_record_idempotent(session_adapter):
    """Recording the same payee twice must not create duplicate entries."""
    user_id = "usr_idem_payee"
    await session_adapter.record_payee(user_id, "ABC Hardware")
    await session_adapter.record_payee(user_id, "ABC Hardware")

    history = await session_adapter.get_payee_history(user_id)
    assert len(history) == 1


# ---------------------------------------------------------------------------
# Evidence Store Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_get_not_found(evidence_adapter):
    """get_evidence for unknown ID must return None."""
    result = await evidence_adapter.get_evidence("evid_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_evidence_put_and_get(evidence_adapter):
    """put_evidence + get_evidence must roundtrip correctly."""
    evidence_id = f"evid_{uuid.uuid4().hex[:12]}"
    evidence_dict = {
        "evidence_id": evidence_id,
        "user_id": "usr_test",
        "vendor_name": "ABC Hardware Co.",
        "amount": 1850.0,
        "currency": "INR",
        "invoice_number": "INV-042",
        "extraction_confidence": 0.95,
        "extraction_method": "STUB",
    }

    await evidence_adapter.put_evidence(evidence_dict)
    retrieved = await evidence_adapter.get_evidence(evidence_id)

    assert retrieved is not None
    assert retrieved["evidence_id"] == evidence_id
    assert retrieved["vendor_name"] == "ABC Hardware Co."
    assert abs(retrieved["amount"] - 1850.0) < 0.01
    assert retrieved["currency"] == "INR"
    # DynamoDB internal keys must be stripped
    assert "pk" not in retrieved
    assert "sk" not in retrieved


@pytest.mark.asyncio
async def test_evidence_put_is_idempotent(evidence_adapter):
    """Storing the same evidence_id twice must not error (last-write wins)."""
    evidence_id = "evid_idem_test"
    base = {
        "evidence_id": evidence_id,
        "user_id": "usr_idem",
        "vendor_name": "v1",
        "amount": 100.0,
        "currency": "INR",
    }

    await evidence_adapter.put_evidence(base)
    updated = {**base, "vendor_name": "v2", "amount": 200.0}
    await evidence_adapter.put_evidence(updated)

    result = await evidence_adapter.get_evidence(evidence_id)
    assert result is not None
    assert result["vendor_name"] == "v2"
    assert abs(result["amount"] - 200.0) < 0.01


# ---------------------------------------------------------------------------
# Pending Decision Store Tests (FIX 2 — Atomic APPROVED → EXECUTED transition)
# ---------------------------------------------------------------------------

@pytest.fixture()
def pending_adapter():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        _create_sessions_table(ddb)
        from app.adapters.dynamo import DynamoPendingDecisionStoreAdapter
        yield DynamoPendingDecisionStoreAdapter(settings=_SessionsSettings())


@pytest.mark.asyncio
async def test_dynamo_pending_put_and_get(pending_adapter):
    """put_pending_decision + get_pending_decision must roundtrip correctly."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "PENDING",
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)
    retrieved = await pending_adapter.get_pending_decision(decision_id)

    assert retrieved is not None
    assert retrieved["decision_id"] == decision_id
    assert retrieved["status"] == "PENDING"
    assert retrieved["user_id"] == "usr_standard"
    # DynamoDB internal keys must be stripped
    assert "pk" not in retrieved
    assert "sk" not in retrieved


@pytest.mark.asyncio
async def test_dynamo_pending_update_pending_to_approved(pending_adapter):
    """update_pending_decision must atomically transition PENDING → APPROVED."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "PENDING",
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)
    await pending_adapter.update_pending_decision(
        decision_id,
        {"status": "APPROVED", "approved_at": "2026-09-18T00:30:00+00:00"},
    )

    retrieved = await pending_adapter.get_pending_decision(decision_id)
    assert retrieved is not None
    assert retrieved["status"] == "APPROVED"
    assert retrieved["approved_at"] == "2026-09-18T00:30:00+00:00"


@pytest.mark.asyncio
async def test_dynamo_update_rejects_non_pending(pending_adapter):
    """update_pending_decision must reject a record that is not PENDING (replay guard)."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "APPROVED",   # Already approved
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)

    with pytest.raises(RuntimeError) as exc_info:
        await pending_adapter.update_pending_decision(
            decision_id, {"status": "DENIED"}
        )

    assert "no longer PENDING" in str(exc_info.value) or "PENDING" in str(exc_info.value)


@pytest.mark.asyncio
async def test_dynamo_mark_executed_succeeds_when_approved(pending_adapter):
    """mark_executed must atomically transition APPROVED → EXECUTED."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "APPROVED",
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)

    executed_at = "2026-09-18T00:35:00+00:00"
    await pending_adapter.mark_executed(decision_id, executed_at)

    retrieved = await pending_adapter.get_pending_decision(decision_id)
    assert retrieved is not None
    assert retrieved["status"] == "EXECUTED"
    assert retrieved["executed_at"] == executed_at


@pytest.mark.asyncio
async def test_dynamo_mark_executed_rejects_pending(pending_adapter):
    """mark_executed must raise RuntimeError if the record is still PENDING."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "PENDING",
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)

    with pytest.raises(RuntimeError) as exc_info:
        await pending_adapter.mark_executed(decision_id, "2026-09-18T00:35:00+00:00")

    assert "APPROVED" in str(exc_info.value) or "concurrent" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_dynamo_mark_executed_concurrent_guard(pending_adapter):
    """Second concurrent mark_executed must be rejected by the DynamoDB condition."""
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"
    record = {
        "decision_id": decision_id,
        "status": "APPROVED",
        "user_id": "usr_standard",
        "session_id": "sess_test",
        "intent_id": "intent_test",
        "amount": 50000.0,
        "currency": "INR",
        "payee": "ABC Hardware",
        "intent_snapshot": {},
        "signals_snapshot": {},
        "policy_snapshot": {},
        "evidence_id": None,
        "transaction_binding_hash": "sha256:dummy",
        "created_at": "2026-09-18T00:00:00+00:00",
        "expires_at": "2026-09-18T01:00:00+00:00",
    }

    await pending_adapter.put_pending_decision(record)

    # First call succeeds
    await pending_adapter.mark_executed(decision_id, "2026-09-18T00:35:00+00:00")

    # Second call must fail — status is now EXECUTED, not APPROVED
    with pytest.raises(RuntimeError) as exc_info:
        await pending_adapter.mark_executed(decision_id, "2026-09-18T00:35:01+00:00")

    error_msg = str(exc_info.value)
    assert "APPROVED" in error_msg or "concurrent" in error_msg.lower() or "EXECUTED" in error_msg

