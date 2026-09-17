"""
AgentPay Sentinel — Router: Policy

GET /policies/rules  — return active policy rules (read-only)
"""

from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_current_user, get_policy_service
from ..models.policy import PolicyRule
from ..models.user import User
from ..services.policy_service import PolicyService

router = APIRouter(prefix="/policies", tags=["Policy"])


class PolicyListResponse(BaseModel):
    rules: List[PolicyRule]
    total: int
    version: str = "1.0.0"
    note: str = (
        "Rules are evaluated in priority order (lowest number first). "
        "All conditions operate on explicit TransactionSignals — no floating-point score."
    )


@router.get(
    "/rules",
    response_model=PolicyListResponse,
    summary="List active policy rules",
    description="Returns the current active policy rule set in evaluation order.",
)
async def list_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    policy_svc: Annotated[PolicyService, Depends(get_policy_service)],
) -> PolicyListResponse:
    rules = policy_svc.get_rules()
    return PolicyListResponse(rules=rules, total=len(rules))
