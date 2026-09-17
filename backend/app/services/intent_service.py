"""
AgentPay Sentinel — Service: Intent Extraction

Calls the LLMAdapter to parse raw natural language → structured PaymentIntent.
LLM output is ALWAYS schema-validated via Pydantic before returning.
Raw LLM text never reaches the policy engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from ..adapters.base import LLMAdapter
from ..config import get_settings
from ..models.payment_intent import PaymentIntent, IntentStatus


class IntentService:
    def __init__(self, llm_adapter: LLMAdapter) -> None:
        self._llm = llm_adapter
        self._settings = get_settings()

    async def extract_intent(
        self,
        raw_input: str,
        user_id: str,
        session_id: str,
    ) -> PaymentIntent:
        """
        Extract structured PaymentIntent from natural language.

        Security: LLM output is parsed through Pydantic validation.
        Any field that fails validation raises a 422, never propagates bad data.
        """
        if not raw_input or not raw_input.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="raw_input must not be empty.",
            )

        # Call LLM (stub locally, Bedrock on Day 2)
        raw_result = await self._llm.extract_intent(raw_input)

        # Validate and enrich
        try:
            intent = PaymentIntent(
                intent_id=f"intent_{uuid.uuid4().hex[:12]}",
                user_id=user_id,
                session_id=session_id,
                raw_input=raw_input,
                payee=raw_result.get("payee", ""),
                amount=float(raw_result.get("amount", 0)),
                currency=raw_result.get("currency", "INR"),
                purpose=raw_result.get("purpose"),
                payment_method=raw_result.get("payment_method", "UPI"),
                confidence_score=float(raw_result.get("confidence_score", 0.5)),
                extraction_model=raw_result.get("extraction_model", "stub"),
                status=IntentStatus.PENDING_AUTHORIZATION,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Intent extraction produced invalid data: {exc}",
            ) from exc

        # Validate critical fields
        if intent.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Extracted amount must be greater than zero.",
            )
        if not intent.payee.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Extracted payee name must not be empty.",
            )

        return intent
