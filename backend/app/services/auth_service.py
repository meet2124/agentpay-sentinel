"""
AgentPay Sentinel — Service: Auth

Day 1: API-key based sessions using LocalSessionStoreAdapter.
Day 3: Replace with Cognito JWT validation.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status

from ..adapters.base import SessionStoreAdapter
from ..config import get_settings
from ..models.user import User, UserSession


class AuthService:
    def __init__(self, session_store: SessionStoreAdapter) -> None:
        self._store = session_store
        self._settings = get_settings()

    async def create_session(self, user_id: str, api_key: str) -> UserSession:
        """Validate API key and create a new session."""
        # Validate API key → user
        user_data = await self._store.get_user_by_api_key(api_key)  # type: ignore[attr-defined]
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
            )
        if user_data["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key does not match the provided user_id.",
            )
        if not user_data.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive.",
            )

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._settings.SESSION_TTL_SECONDS)

        await self._store.create_session(user_id, session_id, token, expires_at.isoformat())

        return UserSession(
            session_id=session_id,
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )

    async def validate_token(self, token: str) -> User:
        """Validate a bearer token and return the associated User."""
        user, _session_id = await self.validate_token_with_session(token)
        return user

    async def validate_token_with_session(self, token: str) -> tuple[User, str]:
        """
        Validate a bearer token and return (User, session_id).

        Used by the payment evaluation path to propagate the real session_id
        instead of the previously hardcoded 'sess_api'.

        session_id is always a non-empty string (created by create_session).
        In the unlikely event the session record lacks a session_id key
        (e.g. legacy records), we fall back to 'sess_unknown'.
        """
        session = await self._store.get_session(token)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_data = await self._store.get_user(session["user_id"])
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User associated with token no longer exists.",
            )
        session_id = session.get("session_id") or "sess_unknown"
        return User(**user_data), session_id

    async def get_user(self, user_id: str) -> User:
        """Fetch a user by ID directly (internal use)."""
        user_data = await self._store.get_user(user_id)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_id}' not found.",
            )
        return User(**user_data)
