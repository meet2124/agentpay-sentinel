"""
AgentPay Sentinel — Adapters: Abstract Base Classes

Each adapter defines the interface. Implementations:
  local.py  — in-memory stubs for Day 1 local development
  s3.py     — AWS S3 (Phase 3.1)
  dynamo.py — AWS DynamoDB (Phase 3.1)
  bedrock.py — AWS Bedrock (Phase 3.2)

Business logic services depend only on these interfaces,
making AWS swap-in require zero changes to service code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class StorageAdapter(ABC):
    """Abstract storage for evidence files."""

    @abstractmethod
    async def store_file(
        self,
        user_id: str,
        file_id: str,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Store a file. Returns a storage key (s3_key or local path)."""

    @abstractmethod
    async def get_file(self, storage_key: str) -> bytes:
        """Retrieve a file by its storage key."""


class SessionStoreAdapter(ABC):
    """Abstract session / user store."""

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        """Return user dict or None if not found."""

    @abstractmethod
    async def get_user_by_api_key(self, api_key: str) -> Optional[dict[str, Any]]:
        """Return user dict for a given API key, or None if invalid."""

    @abstractmethod
    async def create_session(
        self, user_id: str, session_id: str, token: str, expires_at: str
    ) -> None:
        """Persist a new session."""

    @abstractmethod
    async def get_session(self, token: str) -> Optional[dict[str, Any]]:
        """Return session dict or None if token is invalid/expired."""

    @abstractmethod
    async def get_payee_history(self, user_id: str) -> list[str]:
        """Return list of payee names previously used by this user."""

    @abstractmethod
    async def record_payee(self, user_id: str, payee: str) -> None:
        """Record that this user has paid this payee."""


class AuditStoreAdapter(ABC):
    """Abstract store for tamper-evident audit events."""

    @abstractmethod
    async def put_event(self, event: dict[str, Any]) -> None:
        """Persist a single audit event dict."""

    @abstractmethod
    async def get_events(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        decision_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (events, total_count) for a user."""

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        """Return a single event by ID."""

    @abstractmethod
    async def get_last_event_hash(self, user_id: str) -> str:
        """Return the event_hash of the most recent event for this user, or GENESIS."""


class EvidenceStoreAdapter(ABC):
    """
    Abstract store for parsed Evidence metadata.

    The raw file bytes are handled separately by StorageAdapter (S3 or local dict).
    This adapter stores only the structured Evidence object (as a dict) so that
    evidence can be retrieved by ID across Lambda invocations (AWS mode) or
    within the same process (local mode).
    """

    @abstractmethod
    async def put_evidence(self, evidence_dict: dict[str, Any]) -> None:
        """Persist a serialised Evidence dict, keyed by evidence_id."""

    @abstractmethod
    async def get_evidence(self, evidence_id: str) -> Optional[dict[str, Any]]:
        """Return a serialised Evidence dict by evidence_id, or None if not found."""


class PendingDecisionStoreAdapter(ABC):
    """
    Abstract store for pending human-approval decisions.

    A pending decision is created when policy returns REQUIRE_HUMAN_APPROVAL
    and must be retrievable by decision_id for the /approve and /deny endpoints.

    Security contract:
      - put_pending_decision is called once at creation (immutable snapshot)
      - update_pending_decision is the ONLY mutation path (status transitions)
      - No delete path — decisions are retained for audit purposes
    """

    @abstractmethod
    async def put_pending_decision(self, record: dict[str, Any]) -> None:
        """Persist a new pending decision record, keyed by decision_id."""

    @abstractmethod
    async def get_pending_decision(self, decision_id: str) -> Optional[dict[str, Any]]:
        """Return a pending decision record by decision_id, or None if not found."""

    @abstractmethod
    async def update_pending_decision(
        self, decision_id: str, updates: dict[str, Any]
    ) -> None:
        """
        Apply status-transition updates to an existing pending decision.

        The implementation MUST use a conditional write (e.g. DynamoDB
        ConditionExpression) to guard against concurrent approvals (replay).
        Raises RuntimeError if the record is not found or the condition fails.

        NOTE: This method conditions on status == PENDING.
        To transition APPROVED → EXECUTED, use mark_executed() instead.
        """

    @abstractmethod
    async def mark_executed(
        self, decision_id: str, executed_at: str
    ) -> None:
        """
        Atomically transition a decision from APPROVED to EXECUTED.

        The implementation MUST condition on status == APPROVED so that
        a concurrent call cannot transition the same decision twice.
        Raises RuntimeError if the record is not in APPROVED state or not found.
        """


class LLMAdapter(ABC):
    """
    Abstract LLM interface used for intent extraction and evidence parsing.

    IMPORTANT: This adapter returns structured data that is treated as UNTRUSTED.
    All outputs are schema-validated by the calling service before use.
    Raw LLM text never reaches the policy engine.
    """

    @abstractmethod
    async def extract_intent(self, raw_input: str) -> dict[str, Any]:
        """
        Parse natural language payment instruction → structured dict.
        Must match PaymentIntent schema fields: payee, amount, currency, purpose.
        """

    @abstractmethod
    async def extract_evidence(
        self, file_content: bytes, filename: str, content_type: str
    ) -> dict[str, Any]:
        """
        Parse invoice/receipt document → structured dict.
        Must match Evidence schema fields: vendor_name, amount, currency, invoice_number, line_items.
        """
