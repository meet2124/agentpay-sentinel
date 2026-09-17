"""
AgentPay Sentinel — Adapters: Abstract Base Classes

Each adapter defines the interface. Implementations:
  local.py  — in-memory stubs for Day 1 local development
  s3.py     — AWS S3 (Day 2)
  dynamo.py — AWS DynamoDB (Day 2)
  bedrock.py — AWS Bedrock (Day 2)

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
