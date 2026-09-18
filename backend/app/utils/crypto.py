"""
AgentPay Sentinel — Utility: Cryptographic Helpers

Used by audit_service to build the tamper-evident hash chain.

Chain design:
  event_hash   = SHA-256(canonical_json(event_payload))
  chained_hash = SHA-256(event_hash + ":" + prev_event_hash)

"GENESIS" is used as the prev_event_hash for the first event per user.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


GENESIS_HASH = "GENESIS"


def canonical_json(data: dict[str, Any]) -> str:
    """
    Produce a deterministic, canonical JSON string from a dict.
    Keys are sorted; no extra whitespace.
    Used as the input to sha256_hex.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(payload: str) -> str:
    """Return SHA-256 hex digest of a UTF-8 string, prefixed with 'sha256:'."""
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_event_hash(event_payload: dict[str, Any]) -> str:
    """
    Compute the event_hash for a single audit event.
    Excludes hash fields (event_hash, prev_event_hash, chained_hash)
    so the hash is stable even before chaining.
    """
    payload_without_hashes = {
        k: v
        for k, v in event_payload.items()
        if k not in {"event_hash", "prev_event_hash", "chained_hash"}
    }
    return sha256_hex(canonical_json(payload_without_hashes))


def compute_chained_hash(event_hash: str, prev_event_hash: str) -> str:
    """
    Compute the chained_hash that links this event to the previous one.
    chained_hash = SHA-256(event_hash + ":" + prev_event_hash)
    """
    combined = f"{event_hash}:{prev_event_hash}"
    return sha256_hex(combined)


def verify_chain(
    events: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """
    Verify the integrity of an ordered list of audit events.

    Returns (is_valid, list_of_error_messages).
    is_valid is True only when the list is empty.

    Checks:
    1. Each event's event_hash matches recomputed hash of its payload.
    2. Each event's chained_hash matches SHA-256(event_hash + prev_event_hash).
    3. Each event's prev_event_hash matches the previous event's event_hash.
    """
    errors: list[str] = []

    for i, event in enumerate(events):
        event_id = event.get("event_id", f"[index {i}]")

        # 1. Verify event_hash
        recomputed_event_hash = compute_event_hash(event)
        stored_event_hash = event.get("event_hash", "")
        if recomputed_event_hash != stored_event_hash:
            errors.append(
                f"Event {event_id}: event_hash mismatch "
                f"(stored={stored_event_hash}, computed={recomputed_event_hash})"
            )

        # 2. Verify chained_hash
        stored_prev = event.get("prev_event_hash", GENESIS_HASH)
        recomputed_chained = compute_chained_hash(stored_event_hash, stored_prev)
        stored_chained = event.get("chained_hash", "")
        if recomputed_chained != stored_chained:
            errors.append(
                f"Event {event_id}: chained_hash mismatch "
                f"(stored={stored_chained}, computed={recomputed_chained})"
            )

        # 3. Verify chain linkage to previous event
        if i > 0:
            prev_event_hash = events[i - 1].get("event_hash", GENESIS_HASH)
            if stored_prev != prev_event_hash:
                errors.append(
                    f"Event {event_id}: prev_event_hash does not match "
                    f"previous event's event_hash "
                    f"(stored={stored_prev}, expected={prev_event_hash})"
                )

    return (len(errors) == 0, errors)


def compute_transaction_binding_hash(
    intent_id: str,
    payee: str,
    amount: float,
    currency: str,
    evidence_id: str | None,
) -> str:
    """
    Produce a deterministic, tamper-evident hash that binds a human approval
    to the EXACT transaction represented in the pending decision.

    Canonical form:
      {
        "amount":      "<amount rounded to 2dp as string>",
        "currency":    "<UPPER>",
        "evidence_id": "<evidence_id or empty string>",
        "intent_id":   "<intent_id>",
        "payee":       "<payee stripped and lower-cased>",
      }

    Keys are sorted by canonical_json (sort_keys=True).
    Amount is serialised as a fixed-precision string to avoid float drift.
    Payee is normalised (strip + lower) to prevent trivial bypass via
    trailing spaces or case variations.

    SECURITY: This hash is recomputed at approval time from the STORED
    immutable snapshot. Any change to payee, amount, currency, intent, or
    evidence causes a mismatch and the approval is rejected.
    """
    canonical = {
        "amount":      str(round(amount, 2)),
        "currency":    currency.upper(),
        "evidence_id": evidence_id or "",
        "intent_id":   intent_id,
        "payee":       payee.strip().lower(),
    }
    return sha256_hex(canonical_json(canonical))

