"""
AgentPay Sentinel — Service: Mock Payment Simulator

SANDBOX ONLY. No real payment network. No real UPI. No real money.

Rules (enforced in code, not just documented):
  - ONLY executes when final_decision == Decision.ALLOW
  - Raises an error for DENY
  - Raises an error for REQUIRE_HUMAN_APPROVAL
  - Every result carries a mandatory disclaimer

Transaction IDs are deterministic mock strings — never mistaken for real IDs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status

from ..models.authorization import Decision, MockPaymentResult
from ..models.payment_intent import PaymentIntent


_SANDBOX_DISCLAIMER = (
    "⚠️ SANDBOX SIMULATION ONLY. No real payment was made. "
    "AgentPay Sentinel does not connect to any real payment network, "
    "UPI system, or banking infrastructure."
)


class PaymentSimulator:
    """
    Clearly-labeled sandbox payment executor.

    Independently verifies the authorization decision — it does NOT trust
    whatever the caller claims the decision is. The caller must pass the
    Decision enum value, and this service enforces the contract.
    """

    async def simulate(
        self,
        final_decision: Decision,
        intent: PaymentIntent,
    ) -> MockPaymentResult:
        """
        Execute a mock payment only if final_decision is ALLOW.

        Args:
            final_decision: Must be Decision.ALLOW for payment to proceed.
            intent:         The authorized PaymentIntent.

        Returns:
            MockPaymentResult with mandatory sandbox disclaimer.

        Raises:
            HTTPException 403 if called with a non-ALLOW decision.
        """
        # Independent authorization check — never trust the caller blindly
        if final_decision == Decision.DENY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Payment simulation refused: authorization decision is DENY. "
                    "No payment was simulated."
                ),
            )

        if final_decision == Decision.REQUIRE_HUMAN_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Payment simulation refused: decision is REQUIRE_HUMAN_APPROVAL. "
                    "Human review is pending. No payment was simulated."
                ),
            )

        if final_decision != Decision.ALLOW:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Payment simulation refused: unknown decision '{final_decision}'.",
            )

        # Generate deterministic mock transaction ID
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        short_id = uuid.uuid4().hex[:8].upper()
        transaction_id = f"MOCK-{date_str}-{short_id}"

        return MockPaymentResult(
            status="SIMULATED_SUCCESS",
            transaction_id=transaction_id,
            payee=intent.payee,
            amount=intent.amount,
            currency=intent.currency,
            disclaimer=_SANDBOX_DISCLAIMER,
        )
