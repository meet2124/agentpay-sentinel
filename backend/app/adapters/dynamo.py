"""
AgentPay Sentinel — Adapters: AWS DynamoDB

Implements three adapters over two DynamoDB tables (2-table approved design):

  Table: sentinel-audit
    PK: user_id (S)
    SK: ts_event_id (S)   — format: "{timestamp}#{event_id}"
    GSI: event_id-index   — PK: event_id (S) — for single-event lookups

  Table: sentinel-sessions
    PK: pk (S)
    SK: sk (S)
    TTL attribute: expires_at (N, epoch seconds) — used by DynamoDB native TTL

  Key prefixes in sentinel-sessions:
    USER#{user_id}        / USER#{user_id}         → user profile dict
    APIKEY#{api_key}      / APIKEY#{api_key}        → {"user_id": ...}
    SESSION#{token}       / SESSION#{token}         → session dict + TTL
    PAYEE#{user_id}       / PAYEE#{payee_name}      → {} (existence = seen)
    EVIDENCE#{evidence_id}/ EVIDENCE#{evidence_id}  → Evidence JSON

Security:
  - Table names come from config — never hardcoded in business logic
  - IAM role grants GetItem, PutItem, Query on these tables only
  - No DeleteItem/Scan/UpdateItem — not required for this design
  - Audit events are append-only (no update/delete path)
  - Audit chain integrity computed in Python, not relied on DynamoDB ordering
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .base import AuditStoreAdapter, EvidenceStoreAdapter, SessionStoreAdapter
from ..utils.crypto import GENESIS_HASH

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DynamoDB type helpers
# ---------------------------------------------------------------------------

def _to_dynamo(obj: Any) -> Any:
    """
    Recursively convert Python types for DynamoDB storage.
    DynamoDB cannot store float — convert to Decimal.
    None values are omitted (DynamoDB rejects None attribute values).
    """
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def _from_dynamo(obj: Any) -> Any:
    """Recursively convert DynamoDB types back to Python types."""
    if isinstance(obj, dict):
        return {k: _from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamo(v) for v in obj]
    if isinstance(obj, Decimal):
        # Return int if whole number, float otherwise
        f = float(obj)
        return int(f) if f == int(f) else f
    return obj


# ---------------------------------------------------------------------------
# Audit Store — sentinel-audit table
# ---------------------------------------------------------------------------

class DynamoAuditStoreAdapter(AuditStoreAdapter):
    """
    DynamoDB-backed tamper-evident audit store.

    Table: sentinel-audit
      PK=user_id, SK=ts_event_id (chronological sort)
      GSI event_id-index: PK=event_id (for single-event retrieval)

    All writes are append-only. No event is ever updated or deleted.
    The application (not DynamoDB) is responsible for hash chain integrity.
    """

    def __init__(self, settings: "Settings") -> None:
        if not settings.DYNAMODB_TABLE_AUDIT:
            raise ValueError(
                "DYNAMODB_TABLE_AUDIT must be set when USE_LOCAL_ADAPTERS=False."
            )
        self._table_name = settings.DYNAMODB_TABLE_AUDIT
        _dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        self._table = _dynamodb.Table(self._table_name)
        logger.info(
            "DynamoAuditStoreAdapter initialised",
            extra={"table": self._table_name},
        )

    def _make_sk(self, timestamp: str, event_id: str) -> str:
        """
        Build the sort key for chronological ordering.
        Format: "{iso_timestamp}#{event_id}"
        ISO timestamps sort lexicographically in UTC.
        """
        return f"{timestamp}#{event_id}"

    async def put_event(self, event: dict[str, Any]) -> None:
        """
        Append a single audit event to DynamoDB.

        Item layout:
          pk (PK)         = user_id
          ts_event_id (SK)= "{timestamp}#{event_id}"
          event_id        = event_id (also indexed in GSI)
          + all other event fields (nested dicts allowed via _to_dynamo)
        """
        user_id = event["user_id"]
        event_id = event["event_id"]
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        item = _to_dynamo({
            "pk": user_id,
            "ts_event_id": self._make_sk(timestamp, event_id),
            "event_id": event_id,
            **event,
        })

        try:
            self._table.put_item(Item=item)
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB PutItem (audit) failed",
                extra={"event_id": event_id, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to persist audit event {event_id}: {error_code}"
            ) from exc

        logger.info(
            "Audit event persisted",
            extra={"event_id": event_id, "user_id": user_id},
        )

    async def get_events(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        decision_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Query audit events for a user, newest-first.

        DynamoDB does not support SQL-style OFFSET — we fetch limit+offset items
        and slice. For the audit trail use case (small per-user counts),
        this is acceptable at hackathon scale. A pagination token approach
        can be added as a future improvement.
        """
        fetch_limit = limit + offset
        try:
            response = self._table.query(
                KeyConditionExpression=Key("pk").eq(user_id),
                ScanIndexForward=False,  # newest-first
                Limit=fetch_limit if not decision_filter else 500,  # over-fetch for filter
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB Query (audit) failed",
                extra={"user_id": user_id, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to query audit events for user {user_id}: {error_code}"
            ) from exc

        items = [_from_dynamo(item) for item in response.get("Items", [])]

        # Remove DynamoDB-internal keys before returning to callers
        events = [
            {k: v for k, v in item.items() if k not in {"pk", "ts_event_id"}}
            for item in items
        ]

        if decision_filter:
            events = [e for e in events if e.get("decision") == decision_filter]

        total = len(events)
        return events[offset: offset + limit], total

    async def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a single audit event by event_id using the GSI.
        GSI name: event_id-index (PK=event_id).
        """
        try:
            response = self._table.query(
                IndexName="event_id-index",
                KeyConditionExpression=Key("event_id").eq(event_id),
                Limit=1,
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB GSI Query (audit event) failed",
                extra={"event_id": event_id, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to retrieve audit event {event_id}: {error_code}"
            ) from exc

        items = response.get("Items", [])
        if not items:
            return None

        item = _from_dynamo(items[0])
        return {k: v for k, v in item.items() if k not in {"pk", "ts_event_id"}}

    async def get_last_event_hash(self, user_id: str) -> str:
        """
        Return the event_hash of the most recent audit event for this user.
        Returns GENESIS_HASH if no events exist yet.

        Used by AuditService to compute chained_hash for the next event.
        """
        try:
            response = self._table.query(
                KeyConditionExpression=Key("pk").eq(user_id),
                ScanIndexForward=False,  # newest-first
                Limit=1,
                ProjectionExpression="event_hash",
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB Query (last hash) failed",
                extra={"user_id": user_id, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to get last event hash for user {user_id}: {error_code}"
            ) from exc

        items = response.get("Items", [])
        if not items:
            return GENESIS_HASH

        return str(items[0].get("event_hash", GENESIS_HASH))


# ---------------------------------------------------------------------------
# Session / User / Payee / Evidence Store — sentinel-sessions table
# ---------------------------------------------------------------------------

# Pre-loaded demo users (mirroring local.py — seeded into DynamoDB at deploy time)
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

_API_KEYS: dict[str, str] = {
    "sk-dev-basic": "usr_basic",
    "sk-dev-standard": "usr_standard",
    "sk-dev-premium": "usr_premium",
    "sk-test-abc123": "usr_standard",
}


class DynamoSessionStoreAdapter(SessionStoreAdapter):
    """
    DynamoDB-backed store for sessions, users, payee history, and evidence metadata.

    Table: sentinel-sessions (single-table design with key prefixes)

    Key patterns:
      USER#{user_id}          / USER#{user_id}      → user profile
      APIKEY#{api_key}        / APIKEY#{api_key}    → {"user_id": "..."}
      SESSION#{token}         / SESSION#{token}     → session + TTL
      PAYEE#{user_id}         / PAYEE#{payee_name}  → {} (presence = seen)
      EVIDENCE#{evidence_id}  / EVIDENCE#{ev_id}   → evidence JSON

    NOTE: Evidence metadata is stored here (2-table design per approved plan).
    DynamoEvidenceStoreAdapter below is a thin wrapper around this same table.
    """

    def __init__(self, settings: "Settings") -> None:
        if not settings.DYNAMODB_TABLE_SESSIONS:
            raise ValueError(
                "DYNAMODB_TABLE_SESSIONS must be set when USE_LOCAL_ADAPTERS=False."
            )
        self._table_name = settings.DYNAMODB_TABLE_SESSIONS
        self._ttl_seconds = settings.SESSION_TTL_SECONDS
        _dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        self._table = _dynamodb.Table(self._table_name)
        logger.info(
            "DynamoSessionStoreAdapter initialised",
            extra={"table": self._table_name},
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_item(self, pk: str, sk: str) -> Optional[dict[str, Any]]:
        """Fetch a single item by PK+SK. Returns None if not found."""
        try:
            response = self._table.get_item(Key={"pk": pk, "sk": sk})
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB GetItem failed",
                extra={"pk": pk, "sk": sk, "error_code": error_code},
            )
            raise RuntimeError(
                f"DynamoDB GetItem failed for pk={pk}: {error_code}"
            ) from exc

        item = response.get("Item")
        return _from_dynamo(item) if item else None

    def _put_item(self, item: dict[str, Any]) -> None:
        """Write an item unconditionally."""
        try:
            self._table.put_item(Item=_to_dynamo(item))
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            pk = item.get("pk", "?")
            logger.error(
                "DynamoDB PutItem failed",
                extra={"pk": pk, "error_code": error_code},
            )
            raise RuntimeError(
                f"DynamoDB PutItem failed for pk={pk}: {error_code}"
            ) from exc

    # ── User lookup ───────────────────────────────────────────────────────────

    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        """Look up a user by user_id. Falls back to in-memory demo users."""
        pk = f"USER#{user_id}"
        item = self._get_item(pk, pk)
        if item:
            # Strip DynamoDB internal keys
            return {k: v for k, v in item.items() if k not in {"pk", "sk"}}

        # Fallback: return demo user if present (avoids requiring seed step for demos)
        if user_id in _DEMO_USERS:
            logger.debug(
                "User not in DynamoDB — serving from in-memory demo fixture",
                extra={"user_id": user_id},
            )
            return dict(_DEMO_USERS[user_id])

        return None

    async def get_user_by_api_key(self, api_key: str) -> Optional[dict[str, Any]]:
        """Map API key → user_id → user dict."""
        pk = f"APIKEY#{api_key}"
        item = self._get_item(pk, pk)
        if item:
            user_id = item.get("user_id")
            if user_id:
                return await self.get_user(user_id)

        # Fallback: use in-memory API key map for demo keys
        user_id = _API_KEYS.get(api_key)
        if user_id:
            logger.debug(
                "API key not in DynamoDB — serving from in-memory demo fixture",
                extra={"api_key_prefix": api_key[:8]},
            )
            return await self.get_user(user_id)

        return None

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(
        self, user_id: str, session_id: str, token: str, expires_at: str
    ) -> None:
        """Persist a new session with native DynamoDB TTL."""
        # Compute epoch seconds for DynamoDB TTL
        expires_dt = datetime.fromisoformat(expires_at)
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        expires_epoch = int(expires_dt.timestamp())

        pk = f"SESSION#{token}"
        self._put_item({
            "pk": pk,
            "sk": pk,
            "session_id": session_id,
            "user_id": user_id,
            "token": token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at_epoch": expires_epoch,  # DynamoDB TTL attribute
        })

    async def get_session(self, token: str) -> Optional[dict[str, Any]]:
        """Retrieve a session by bearer token. Returns None if expired or missing."""
        pk = f"SESSION#{token}"
        item = self._get_item(pk, pk)
        if not item:
            return None

        # Guard: also check expiry in Python (TTL deletion is eventually consistent)
        expires_at = item.get("expires_at")
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_dt:
                return None

        return {k: v for k, v in item.items() if k not in {"pk", "sk", "expires_at_epoch"}}

    # ── Payee history ─────────────────────────────────────────────────────────

    async def get_payee_history(self, user_id: str) -> list[str]:
        """Return list of normalised payee names previously used by this user."""
        try:
            response = self._table.query(
                KeyConditionExpression=Key("pk").eq(f"PAYEE#{user_id}"),
            )
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "DynamoDB Query (payee history) failed",
                extra={"user_id": user_id, "error_code": error_code},
            )
            raise RuntimeError(
                f"Failed to query payee history for user {user_id}: {error_code}"
            ) from exc

        # SK is the normalised payee name
        return [
            item["sk"].replace("PAYEE#", "", 1) if item["sk"].startswith("PAYEE#") else item["sk"]
            for item in response.get("Items", [])
        ]

    async def record_payee(self, user_id: str, payee: str) -> None:
        """Record that this user has paid this payee (idempotent)."""
        normalised = payee.strip().lower()
        self._put_item({
            "pk": f"PAYEE#{user_id}",
            "sk": f"PAYEE#{normalised}",
        })

    # ── Evidence metadata (stored in sentinel-sessions per 2-table design) ────

    def _put_evidence(self, evidence_dict: dict[str, Any]) -> None:
        evidence_id = evidence_dict["evidence_id"]
        pk = f"EVIDENCE#{evidence_id}"
        self._put_item({
            "pk": pk,
            "sk": pk,
            **evidence_dict,
        })

    def _get_evidence(self, evidence_id: str) -> Optional[dict[str, Any]]:
        pk = f"EVIDENCE#{evidence_id}"
        item = self._get_item(pk, pk)
        if not item:
            return None
        return {k: v for k, v in item.items() if k not in {"pk", "sk"}}


# ---------------------------------------------------------------------------
# Evidence Store — thin wrapper around DynamoSessionStoreAdapter
# ---------------------------------------------------------------------------

class DynamoEvidenceStoreAdapter(EvidenceStoreAdapter):
    """
    DynamoDB-backed evidence metadata store.

    Uses the sentinel-sessions table with EVIDENCE# key prefix
    (approved 2-table design).

    The raw file bytes are stored separately in S3 (S3StorageAdapter).
    This adapter stores only the parsed Evidence metadata.
    """

    def __init__(self, settings: "Settings") -> None:
        # Reuses the same table as DynamoSessionStoreAdapter
        self._sessions_adapter = DynamoSessionStoreAdapter(settings)

    async def put_evidence(self, evidence_dict: dict[str, Any]) -> None:
        self._sessions_adapter._put_evidence(evidence_dict)

    async def get_evidence(self, evidence_id: str) -> Optional[dict[str, Any]]:
        return self._sessions_adapter._get_evidence(evidence_id)
