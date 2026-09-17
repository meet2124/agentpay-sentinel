"""
AgentPay Sentinel — Service: Comparison / Signal Computation

Computes TransactionSignals from PaymentIntent + Evidence + User context.
Every computation is deterministic — no LLM calls.
"""

from __future__ import annotations

from typing import Optional

from ..config import get_settings
from ..models.evidence import Evidence
from ..models.payment_intent import PaymentIntent
from ..models.signals import TransactionSignals
from ..models.user import User
from ..utils.fuzzy import payee_matches, payee_similarity


class ComparisonService:
    """
    Deterministic signal computation.

    Inputs:  PaymentIntent, Evidence | None, User
    Outputs: TransactionSignals

    No LLM is called here.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def compute_signals(
        self,
        intent: PaymentIntent,
        evidence: Optional[Evidence],
        user: User,
        payee_history: list[str],
    ) -> TransactionSignals:
        """
        Compute all explicit transaction signals.

        Args:
            intent:         Validated PaymentIntent
            evidence:       Extracted Evidence or None
            user:           Authenticated User
            payee_history:  List of lowercase payee names previously paid by this user
        """
        cfg = self._settings

        # --- Evidence presence & quality ---
        evidence_present = evidence is not None
        evidence_extraction_confidence = (
            evidence.extraction_confidence if evidence else 0.0
        )
        evidence_extraction_ok = (
            evidence_present
            and evidence_extraction_confidence >= cfg.EVIDENCE_CONFIDENCE_THRESHOLD
        )

        # --- Amount comparison ---
        if evidence_present and evidence.amount is not None:
            amount_delta = abs(intent.amount - evidence.amount)
            amount_match = amount_delta <= cfg.AMOUNT_MATCH_THRESHOLD_INR
        else:
            amount_delta = 0.0
            # No evidence → amount_match is vacuously True (but evidence_present=False will drive policy)
            amount_match = not evidence_present

        # --- Payee comparison ---
        if evidence_present and evidence.vendor_name:
            sim = payee_similarity(intent.payee, evidence.vendor_name)
            p_match = sim >= cfg.PAYEE_MATCH_THRESHOLD
        else:
            sim = 0.0
            # No evidence → payee_match is vacuously True (policy uses evidence_present)
            p_match = not evidence_present

        # --- Currency comparison ---
        if evidence_present and evidence.currency:
            currency_match = intent.currency.upper() == evidence.currency.upper()
        else:
            currency_match = True  # vacuously True when no evidence

        # --- Spending limit ---
        amount_within_limit = intent.amount <= user.spending_limit_inr
        amount_vs_limit_ratio = intent.amount / user.spending_limit_inr

        # --- Payee history ---
        payee_seen_before = intent.payee.strip().lower() in [p.lower() for p in payee_history]

        # --- display_risk_score (UI only — NOT used in policy conditions) ---
        display_risk_score = self._compute_display_score(
            evidence_present=evidence_present,
            evidence_extraction_ok=evidence_extraction_ok,
            amount_match=amount_match,
            payee_match=p_match,
            currency_match=currency_match,
            amount_within_limit=amount_within_limit,
            payee_seen_before=payee_seen_before,
        )

        return TransactionSignals(
            intent_id=intent.intent_id,
            evidence_id=evidence.evidence_id if evidence else None,
            amount_match=amount_match,
            amount_delta_inr=round(amount_delta, 2),
            payee_match=p_match,
            payee_similarity=round(sim, 4),
            evidence_present=evidence_present,
            evidence_extraction_ok=evidence_extraction_ok,
            evidence_extraction_confidence=round(evidence_extraction_confidence, 4),
            currency_match=currency_match,
            amount_within_limit=amount_within_limit,
            amount_vs_limit_ratio=round(amount_vs_limit_ratio, 4),
            payee_seen_before=payee_seen_before,
            display_risk_score=display_risk_score,
        )

    @staticmethod
    def _compute_display_score(
        *,
        evidence_present: bool,
        evidence_extraction_ok: bool,
        amount_match: bool,
        payee_match: bool,
        currency_match: bool,
        amount_within_limit: bool,
        payee_seen_before: bool,
    ) -> int:
        """
        Derive a 0–100 display score from signal values.
        Higher score = more concern.  Used ONLY for the UI gauge.
        Never referenced in any policy rule.
        """
        score = 0
        if not evidence_present:
            score += 25
        if evidence_present and not evidence_extraction_ok:
            score += 20
        if evidence_present and not amount_match:
            score += 30
        if evidence_present and not payee_match:
            score += 25
        if not currency_match:
            score += 10
        if not amount_within_limit:
            score += 20
        if not payee_seen_before:
            score += 5
        return min(score, 100)
