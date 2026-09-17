"""
AgentPay Sentinel — Service: Tamper-Evident Audit Trail

Writes audit events BEFORE the API response is returned (audit-first design).

Hash chain design:
  event_hash   = SHA-256(canonical JSON of event payload, excluding hash fields)
  chained_hash = SHA-256(event_hash + ":" + prev_event_hash)

"GENESIS" is the prev_event_hash for the first event per user.
Tampering with any past event breaks all subsequent chained_hashes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..adapters.base import AuditStoreAdapter
from ..models.audit import AuditEvent, AuditEventType
from ..utils.crypto import compute_chained_hash, compute_event_hash


class AuditService:
    def __init__(self, audit_store: AuditStoreAdapter) -> None:
        self._store = audit_store

    async def record(
        self,
        *,
        event_type: AuditEventType,
        user_id: str,
        session_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        evidence_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        decision: Optional[str] = None,
        intent_snapshot: Optional[dict[str, Any]] = None,
        evidence_snapshot: Optional[dict[str, Any]] = None,
        signals_snapshot: Optional[dict[str, Any]] = None,
        policy_snapshot: Optional[dict[str, Any]] = None,
        payment_result_snapshot: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Create and persist one audit event with tamper-evident hash chain.
        Must be called BEFORE returning the API response.
        """
        event_id = f"audit_{uuid.uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc)

        # Build the payload dict (without hash fields) for hashing
        payload: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type.value,
            "user_id": user_id,
            "session_id": session_id,
            "intent_id": intent_id,
            "evidence_id": evidence_id,
            "decision_id": decision_id,
            "decision": decision,
            "intent_snapshot": intent_snapshot,
            "evidence_snapshot": evidence_snapshot,
            "signals_snapshot": signals_snapshot,
            "policy_snapshot": policy_snapshot,
            "payment_result_snapshot": payment_result_snapshot,
            "timestamp": timestamp.isoformat(),
        }

        # Fetch the previous event hash for this user (GENESIS if first)
        prev_event_hash = await self._store.get_last_event_hash(user_id)

        # Compute hashes
        event_hash = compute_event_hash(payload)
        chained_hash = compute_chained_hash(event_hash, prev_event_hash)

        # Add hashes to payload
        payload["event_hash"] = event_hash
        payload["prev_event_hash"] = prev_event_hash
        payload["chained_hash"] = chained_hash

        # Persist event BEFORE returning
        await self._store.put_event(payload)

        return AuditEvent(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            intent_id=intent_id,
            evidence_id=evidence_id,
            decision_id=decision_id,
            decision=decision,
            intent_snapshot=intent_snapshot,
            evidence_snapshot=evidence_snapshot,
            signals_snapshot=signals_snapshot,
            policy_snapshot=policy_snapshot,
            payment_result_snapshot=payment_result_snapshot,
            event_hash=event_hash,
            prev_event_hash=prev_event_hash,
            chained_hash=chained_hash,
            timestamp=timestamp,
        )

    async def get_events(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        decision_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._store.get_events(
            user_id=user_id,
            limit=limit,
            offset=offset,
            decision_filter=decision_filter,
        )

    async def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        return await self._store.get_event(event_id)
