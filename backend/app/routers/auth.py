"""
AgentPay Sentinel — Router: Auth

POST /auth/session  — create session from API key
GET  /auth/me       — return current user
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..dependencies import get_auth_service, get_current_user
from ..models.user import (
    SessionCreateRequest,
    SessionCreateResponse,
    User,
    UserSession,
)
from ..services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/session",
    response_model=SessionCreateResponse,
    summary="Create a new session",
    description="Authenticate with an API key and receive a bearer token.",
)
async def create_session(
    body: SessionCreateRequest,
    auth_svc: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionCreateResponse:
    session: UserSession = await auth_svc.create_session(
        user_id=body.user_id,
        api_key=body.api_key,
    )
    user = await auth_svc.get_user(session.user_id)
    return SessionCreateResponse(
        session_id=session.session_id,
        token=session.token,
        expires_at=session.expires_at,
        user=user,
    )


@router.get(
    "/me",
    response_model=User,
    summary="Get current user",
    description="Return the authenticated user associated with the bearer token.",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
