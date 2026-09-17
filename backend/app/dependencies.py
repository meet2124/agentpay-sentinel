"""
AgentPay Sentinel — Dependency Injection Container

Provides FastAPI dependency functions that wire together adapters and services.
Switching from local to AWS adapters requires changing only this file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .adapters.local import (
    LocalAuditStoreAdapter,
    LocalLLMAdapter,
    LocalSessionStoreAdapter,
    LocalStorageAdapter,
)
from .config import Settings, get_settings
from .models.user import User
from .services.audit_service import AuditService
from .services.auth_service import AuthService
from .services.authorization_service import AuthorizationService
from .services.comparison_service import ComparisonService
from .services.evidence_service import EvidenceService
from .services.intent_service import IntentService
from .services.payment_simulator import PaymentSimulator
from .services.policy_service import PolicyService


# ---------------------------------------------------------------------------
# Adapter singletons (module-level — shared across requests)
# ---------------------------------------------------------------------------

_session_store = LocalSessionStoreAdapter()
_storage       = LocalStorageAdapter()
_llm           = LocalLLMAdapter()
_audit_store   = LocalAuditStoreAdapter()


# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

_auth_service       = AuthService(session_store=_session_store)
_intent_service     = IntentService(llm_adapter=_llm)
_evidence_service   = EvidenceService(storage_adapter=_storage, llm_adapter=_llm)
_comparison_service = ComparisonService()
_policy_service     = PolicyService()
_audit_service      = AuditService(audit_store=_audit_store)
_payment_simulator  = PaymentSimulator()
_authorization_service = AuthorizationService(
    intent_service=_intent_service,
    evidence_service=_evidence_service,
    comparison_service=_comparison_service,
    policy_service=_policy_service,
    audit_service=_audit_service,
    payment_simulator=_payment_simulator,
    session_store=_session_store,
)


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------

def get_auth_service() -> AuthService:
    return _auth_service


def get_authorization_service() -> AuthorizationService:
    return _authorization_service


def get_evidence_service() -> EvidenceService:
    return _evidence_service


def get_audit_service() -> AuditService:
    return _audit_service


def get_policy_service() -> PolicyService:
    return _policy_service


def get_session_store() -> LocalSessionStoreAdapter:
    return _session_store  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Auth dependency — extracts and validates Bearer token
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
    auth_svc: AuthService = Depends(get_auth_service),
) -> User:
    """FastAPI dependency: validate Bearer token → return User."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required (Bearer token).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await auth_svc.validate_token(credentials.credentials)
