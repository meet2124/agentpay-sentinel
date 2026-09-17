"""
AgentPay Sentinel — Service: Policy Engine

Evaluates the MVP_POLICY_RULES in priority order against TransactionSignals.
First matching rule wins.

CRITICAL: This is the only place where the authorization decision is made.
The LLM never reaches this function.
All inputs are validated Python objects, not raw strings.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..config import get_settings
from ..models.payment_intent import PaymentIntent
from ..models.policy import MVP_POLICY_RULES, PolicyDecision, PolicyResult, PolicyRule
from ..models.signals import TransactionSignals


class PolicyService:
    """
    Priority-ordered rule evaluation.

    Rules are loaded from MVP_POLICY_RULES (models/policy.py).
    Each rule is evaluated as a Python boolean expression against TransactionSignals.
    No floating-point score, no LLM output, no dynamic rule injection.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        # Load and sort rules by priority (ascending = highest priority first)
        self._rules: list[PolicyRule] = sorted(
            [PolicyRule(**r) for r in MVP_POLICY_RULES if r.get("is_active", True)],
            key=lambda r: r.priority,
        )

    def evaluate(
        self,
        signals: TransactionSignals,
        intent: PaymentIntent,
    ) -> PolicyResult:
        """
        Evaluate all active rules against the given signals.
        Returns the first matching PolicyResult.

        If no rule matches (shouldn't happen with a properly configured rule set),
        defaults to DENY for safety.
        """
        matched_rule_ids: list[str] = []
        reason_parts: list[str] = []

        for rule in self._rules:
            matched = self._evaluate_rule(rule, signals, intent)
            if matched:
                matched_rule_ids.append(rule.rule_id)
                reason_parts.append(self._build_reason(rule, signals, intent))
                # First-match wins
                return PolicyResult(
                    intent_id=signals.intent_id,
                    decision=rule.action,
                    matched_rule_ids=matched_rule_ids,
                    evaluated_rule_count=len(self._rules),
                    reason="; ".join(reason_parts),
                    evaluated_at=datetime.now(timezone.utc),
                )

        # Safety default — should never be reached with complete rule set
        return PolicyResult(
            intent_id=signals.intent_id,
            decision=PolicyDecision.DENY,
            matched_rule_ids=["__safety_default__"],
            evaluated_rule_count=len(self._rules),
            reason="No policy rule matched — denied by safety default.",
            evaluated_at=datetime.now(timezone.utc),
        )

    def get_rules(self) -> list[PolicyRule]:
        """Return the active sorted rule set."""
        return list(self._rules)

    def _evaluate_rule(
        self,
        rule: PolicyRule,
        signals: TransactionSignals,
        intent: PaymentIntent,
    ) -> bool:
        """
        Evaluate a single rule against the signals.
        Conditions mirror architecture.md exactly.
        Each branch maps 1:1 to a row in the policy table.
        """
        cfg = self._settings

        if rule.rule_id == "deny_evidence_missing_high_amount":
            return (
                not signals.evidence_present
                and intent.amount > cfg.SMALL_PAYMENT_LIMIT_INR
            )

        if rule.rule_id == "deny_amount_mismatch":
            return signals.evidence_present and not signals.amount_match

        if rule.rule_id == "deny_payee_mismatch":
            return signals.evidence_present and not signals.payee_match

        if rule.rule_id == "deny_low_confidence_extraction":
            return signals.evidence_present and not signals.evidence_extraction_ok

        if rule.rule_id == "human_approval_exceeds_limit":
            return not signals.amount_within_limit

        if rule.rule_id == "human_approval_unknown_payee_medium_amount":
            return (
                not signals.payee_seen_before
                and intent.amount > cfg.UNKNOWN_PAYEE_MEDIUM_AMOUNT_INR
            )

        if rule.rule_id == "allow_full_match":
            return (
                signals.amount_match
                and signals.payee_match
                and signals.evidence_present
                and signals.amount_within_limit
            )

        if rule.rule_id == "allow_small_no_evidence":
            return (
                not signals.evidence_present
                and intent.amount <= cfg.SMALL_PAYMENT_LIMIT_INR
                and signals.amount_within_limit
            )

        # Unknown rule — skip (safe default)
        return False

    def _build_reason(
        self,
        rule: PolicyRule,
        signals: TransactionSignals,
        intent: PaymentIntent,
    ) -> str:
        """Build a human-readable reason string for the matched rule."""
        if rule.rule_id == "deny_evidence_missing_high_amount":
            return (
                f"No evidence provided for a payment of ₹{intent.amount:,.2f}. "
                f"Evidence is required for amounts above ₹{self._settings.SMALL_PAYMENT_LIMIT_INR:,.0f}."
            )
        if rule.rule_id == "deny_amount_mismatch":
            return (
                f"Amount mismatch: agent requested ₹{intent.amount:,.2f} but "
                f"evidence shows ₹{intent.amount - signals.amount_delta_inr:,.2f} "
                f"(delta: ₹{signals.amount_delta_inr:,.2f})."
            )
        if rule.rule_id == "deny_payee_mismatch":
            return (
                f"Payee mismatch: agent specified '{intent.payee}' but evidence "
                f"names a different vendor "
                f"(similarity: {signals.payee_similarity:.0%}, threshold: "
                f"{self._settings.PAYEE_MATCH_THRESHOLD:.0%})."
            )
        if rule.rule_id == "deny_low_confidence_extraction":
            return (
                f"Evidence extraction confidence too low "
                f"({signals.evidence_extraction_confidence:.0%} < "
                f"{self._settings.EVIDENCE_CONFIDENCE_THRESHOLD:.0%}). "
                "Cannot reliably verify intent against evidence."
            )
        if rule.rule_id == "human_approval_exceeds_limit":
            return (
                f"Amount ₹{intent.amount:,.2f} exceeds your spending limit of "
                f"₹{intent.amount / signals.amount_vs_limit_ratio:,.2f}. "
                "Human approval required."
            )
        if rule.rule_id == "human_approval_unknown_payee_medium_amount":
            return (
                f"'{intent.payee}' is a new payee for this account and the amount "
                f"₹{intent.amount:,.2f} exceeds ₹{self._settings.UNKNOWN_PAYEE_MEDIUM_AMOUNT_INR:,.0f}. "
                "Human approval required."
            )
        if rule.rule_id == "allow_full_match":
            return (
                f"All checks passed: amount matches (delta ₹{signals.amount_delta_inr:,.2f}), "
                f"payee matches ({signals.payee_similarity:.0%} similarity), "
                "evidence present and within spending limit."
            )
        if rule.rule_id == "allow_small_no_evidence":
            return (
                f"Small payment of ₹{intent.amount:,.2f} is below the evidence threshold "
                f"(₹{self._settings.SMALL_PAYMENT_LIMIT_INR:,.0f}) and within spending limit."
            )
        return rule.description
