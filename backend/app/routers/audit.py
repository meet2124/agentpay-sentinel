"""
AgentPay Sentinel — Router: Audit Trail

GET /audit/events         — list tamper-evident audit events for current user
GET /audit/events/{id}    — get single audit event
GET /audit/verify         — verify hash chain integrity for current user
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..dependencies import get_audit_service, get_current_user
from ..models.audit import AuditEvent
from ..models.user import User
from ..services.audit_service import AuditService
from ..utils.crypto import verify_chain

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


class AuditListResponse(BaseModel):
    events: List[dict]
    total: int
    offset: int
    limit: int


class ChainVerifyResponse(BaseModel):
    user_id: str
    events_checked: int
    chain_valid: bool
    errors: List[str]


@router.get(
    "/events",
    response_model=AuditListResponse,
    summary="List audit events",
    description=(
        "Returns tamper-evident audit trail events for the authenticated user. "
        "Each event includes event_hash, prev_event_hash, and chained_hash "
        "for independent verification."
    ),
)
async def list_events(
    current_user: Annotated[User, Depends(get_current_user)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision: Optional[str] = Query(default=None, description="Filter by ALLOW|DENY|REQUIRE_HUMAN_APPROVAL"),
) -> AuditListResponse:
    events, total = await audit_svc.get_events(
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
        decision_filter=decision,
    )
    return AuditListResponse(events=events, total=total, offset=offset, limit=limit)


@router.get(
    "/events/{event_id}",
    summary="Get single audit event",
)
async def get_event(
    event_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> dict:
    event = await audit_svc.get_event(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit event '{event_id}' not found.",
        )
    if event.get("user_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this audit event.",
        )
    return event


@router.get(
    "/verify",
    response_model=ChainVerifyResponse,
    summary="Verify hash chain integrity",
    description=(
        "Recomputes the tamper-evident hash chain for all audit events "
        "belonging to the authenticated user. "
        "Returns chain_valid=false and error details if any tampering is detected."
    ),
)
async def verify_chain_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    audit_svc: Annotated[AuditService, Depends(get_audit_service)],
) -> ChainVerifyResponse:
    # Fetch ALL events for this user in chronological order (oldest first)
    all_events, total = await audit_svc.get_events(
        user_id=current_user.user_id,
        limit=10000,
        offset=0,
    )
    # get_events returns newest-first; reverse to oldest-first for chain verification
    all_events_asc = list(reversed(all_events))

    is_valid, errors = verify_chain(all_events_asc)
    return ChainVerifyResponse(
        user_id=current_user.user_id,
        events_checked=len(all_events_asc),
        chain_valid=is_valid,
        errors=errors,
    )
