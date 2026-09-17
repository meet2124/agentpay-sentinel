"""
AgentPay Sentinel — Adapters: Local In-Memory Implementations

Used for Day 1 local development. No external dependencies.
All data is stored in module-level dicts (process lifetime only).

Swap for AWS adapters (s3.py, dynamo.py, bedrock.py) when USE_LOCAL_ADAPTERS=False.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .base import AuditStoreAdapter, LLMAdapter, SessionStoreAdapter, StorageAdapter
from ..utils.crypto import GENESIS_HASH


# ---------------------------------------------------------------------------
# Pre-loaded demo users (Day 1 auth — no Cognito yet)
# ---------------------------------------------------------------------------

_DEMO_USERS: dict[str, dict] = {
    "usr_basic": {
        "user_id": "usr_basic",
        "name": "Ananya Patel",
        "email": "ananya@example.com",
        "tier": "BASIC",
        "spending_limit_inr": 1000.0,
        "daily_limit_inr": 5000.0,
        "created_at": "2026-01-01T00:00:00",
        "is_active": True,
    },
    "usr_standard": {
        "user_id": "usr_standard",
        "name": "Priya Sharma",
        "email": "priya@example.com",
        "tier": "STANDARD",
        "spending_limit_inr": 10000.0,
        "daily_limit_inr": 50000.0,
        "created_at": "2026-01-01T00:00:00",
        "is_active": True,
    },
    "usr_premium": {
        "user_id": "usr_premium",
        "name": "Arjun Singh",
        "email": "arjun@example.com",
        "tier": "PREMIUM",
        "spending_limit_inr": 50000.0,
        "daily_limit_inr": 200000.0,
        "created_at": "2026-01-01T00:00:00",
        "is_active": True,
    },
}

# API keys → user_id mapping (dev only — never do this in production)
_API_KEYS: dict[str, str] = {
    "sk-dev-basic": "usr_basic",
    "sk-dev-standard": "usr_standard",
    "sk-dev-premium": "usr_premium",
    # Convenience alias
    "sk-test-abc123": "usr_standard",
}


# ---------------------------------------------------------------------------
# In-memory stores (process lifetime)
# ---------------------------------------------------------------------------
_file_store: dict[str, bytes] = {}
_session_store: dict[str, dict] = {}   # token → session dict
_payee_history: dict[str, list[str]] = {}  # user_id → [payee names]
_audit_store: dict[str, dict] = {}     # event_id → event dict
_audit_order: dict[str, list[str]] = {}  # user_id → [event_ids in order]


# ---------------------------------------------------------------------------
# Storage Adapter — Local
# ---------------------------------------------------------------------------

class LocalStorageAdapter(StorageAdapter):
    """Stores file bytes in a module-level dict."""

    async def store_file(
        self,
        user_id: str,
        file_id: str,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        key = f"local/{user_id}/{file_id}/{filename}"
        _file_store[key] = content
        return key

    async def get_file(self, storage_key: str) -> bytes:
        if storage_key not in _file_store:
            raise FileNotFoundError(f"File not found: {storage_key}")
        return _file_store[storage_key]


# ---------------------------------------------------------------------------
# Session / User Store Adapter — Local
# ---------------------------------------------------------------------------

class LocalSessionStoreAdapter(SessionStoreAdapter):

    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        return copy.deepcopy(_DEMO_USERS.get(user_id))

    async def get_user_by_api_key(self, api_key: str) -> Optional[dict[str, Any]]:
        user_id = _API_KEYS.get(api_key)
        if not user_id:
            return None
        return await self.get_user(user_id)

    async def create_session(
        self, user_id: str, session_id: str, token: str, expires_at: str
    ) -> None:
        _session_store[token] = {
            "session_id": session_id,
            "user_id": user_id,
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_session(self, token: str) -> Optional[dict[str, Any]]:
        session = _session_store.get(token)
        if not session:
            return None
        # Check expiry
        expires_at = datetime.fromisoformat(session["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            _session_store.pop(token, None)
            return None
        return copy.deepcopy(session)

    async def get_payee_history(self, user_id: str) -> list[str]:
        return list(_payee_history.get(user_id, []))

    async def record_payee(self, user_id: str, payee: str) -> None:
        if user_id not in _payee_history:
            _payee_history[user_id] = []
        name = payee.strip().lower()
        if name not in _payee_history[user_id]:
            _payee_history[user_id].append(name)


# ---------------------------------------------------------------------------
# Audit Store Adapter — Local
# ---------------------------------------------------------------------------

class LocalAuditStoreAdapter(AuditStoreAdapter):

    async def put_event(self, event: dict[str, Any]) -> None:
        event_id = event["event_id"]
        user_id = event["user_id"]
        _audit_store[event_id] = copy.deepcopy(event)
        if user_id not in _audit_order:
            _audit_order[user_id] = []
        _audit_order[user_id].append(event_id)

    async def get_events(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        decision_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        event_ids = _audit_order.get(user_id, [])
        events = [copy.deepcopy(_audit_store[eid]) for eid in reversed(event_ids) if eid in _audit_store]
        if decision_filter:
            events = [e for e in events if e.get("decision") == decision_filter]
        total = len(events)
        return events[offset : offset + limit], total

    async def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        ev = _audit_store.get(event_id)
        return copy.deepcopy(ev) if ev else None

    async def get_last_event_hash(self, user_id: str) -> str:
        event_ids = _audit_order.get(user_id, [])
        if not event_ids:
            return GENESIS_HASH
        last_id = event_ids[-1]
        ev = _audit_store.get(last_id, {})
        return ev.get("event_hash", GENESIS_HASH)


# ---------------------------------------------------------------------------
# LLM Adapter — Stub (deterministic fixtures for local dev)
# ---------------------------------------------------------------------------
# The stub parses common patterns from the raw_input string so that tests
# can exercise meaningful data without a real LLM.  Bedrock replaces this on Day 2.
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(r"[₹Rs\.]*\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_PAYEE_RE  = re.compile(r"to\s+(.+?)(?:\s+for|\s+via|\s+as|\.|$)", re.IGNORECASE)


def _parse_amount(text: str) -> float:
    m = _AMOUNT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def _parse_payee(text: str) -> str:
    m = _PAYEE_RE.search(text)
    if m:
        return m.group(1).strip()
    return "Unknown"


class LocalLLMAdapter(LLMAdapter):
    """
    Deterministic stub that extracts intent/evidence via regex/fixtures.
    Returns the same schema that the Bedrock adapter will return on Day 2.
    """

    async def extract_intent(self, raw_input: str) -> dict[str, Any]:
        """Parse raw text into a PaymentIntent-shaped dict."""
        amount = _parse_amount(raw_input)
        payee = _parse_payee(raw_input)

        # Extract purpose (after "for")
        purpose_match = re.search(r"\bfor\s+(.+?)(?:\.|$)", raw_input, re.IGNORECASE)
        purpose = purpose_match.group(1).strip() if purpose_match else None

        return {
            "payee": payee,
            "amount": amount,
            "currency": "INR",
            "purpose": purpose,
            "payment_method": "UPI",
            "confidence_score": 0.90,
            "extraction_model": "stub",
        }

    async def extract_evidence(
        self, file_content: bytes, filename: str, content_type: str
    ) -> dict[str, Any]:
        """
        Attempt to parse JSON-encoded evidence fixture from file content.
        If the file is not valid JSON, return a high-confidence stub
        that mirrors a typical ABC Hardware invoice.
        """
        try:
            data = json.loads(file_content.decode("utf-8"))
            # Ensure required fields exist
            return {
                "vendor_name": data.get("vendor_name", "ABC Hardware Co."),
                "vendor_gstin": data.get("vendor_gstin"),
                "amount": float(data.get("amount", 1850.0)),
                "currency": data.get("currency", "INR"),
                "invoice_number": data.get("invoice_number", "INV-042"),
                "invoice_date": data.get("invoice_date"),
                "line_items": data.get("line_items", []),
                "extraction_confidence": float(data.get("extraction_confidence", 0.92)),
                "extraction_method": "STUB",
            }
        except (json.JSONDecodeError, ValueError):
            # Non-JSON file (e.g., real PDF in tests) → high-confidence stub
            return {
                "vendor_name": "ABC Hardware Co.",
                "vendor_gstin": None,
                "amount": 1850.0,
                "currency": "INR",
                "invoice_number": "INV-042",
                "invoice_date": str(date.today()),
                "line_items": [],
                "extraction_confidence": 0.92,
                "extraction_method": "STUB",
            }
