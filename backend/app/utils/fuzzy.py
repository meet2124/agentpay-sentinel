"""
AgentPay Sentinel — Utility: Fuzzy String Matching

Used for payee name comparison in comparison_service.
Wraps rapidfuzz for token-set ratio matching, which handles
word-order differences and abbreviations well.

Example:
  "ABC Hardware" vs "ABC Hardware Co." → 0.94
  "XYZ Traders"  vs "ABC Hardware Co." → 0.12
"""

from __future__ import annotations

from rapidfuzz import fuzz


def payee_similarity(a: str, b: str) -> float:
    """
    Compute normalized similarity between two payee/vendor name strings.

    Uses token_set_ratio which is robust to:
    - Different word order
    - Abbreviations (e.g., "Co." vs "Company")
    - Extra words (e.g., "ABC Hardware" vs "ABC Hardware Co.")

    Returns a float in [0.0, 1.0].
    """
    if not a or not b:
        return 0.0
    # token_set_ratio returns 0–100, normalize to 0–1
    score = fuzz.token_set_ratio(a.strip(), b.strip())
    return round(score / 100.0, 4)


def payee_matches(a: str, b: str, threshold: float = 0.85) -> bool:
    """Return True if payee_similarity(a, b) >= threshold."""
    return payee_similarity(a, b) >= threshold
