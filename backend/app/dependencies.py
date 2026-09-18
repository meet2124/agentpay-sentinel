"""
AgentPay Sentinel — Dependency Injection Container

Provides FastAPI dependency functions that wire together adapters and services.

Adapter selection:
  USE_LOCAL_ADAPTERS=True  → local in-memory implementations (default, no AWS needed)
  USE_LOCAL_ADAPTERS=False → AWS implementations (S3, DynamoDB)

Switching adapters requires changing only this file.
Service code (policy_service, comparison_service, etc.) is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .adapters.base import (
    AuditStoreAdapter,
    EvidenceStoreAdapter,
    PendingDecisionStoreAdapter,
    SessionStoreAdapter,
    StorageAdapter,
)
from .adapters.local import (
    LocalAuditStoreAdapter,
    LocalEvidenceStoreAdapter,
    LocalLLMAdapter,
    LocalPendingDecisionStoreAdapter,
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
from .services.pending_decision_service import PendingDecisionService
from .services.policy_service import PolicyService


# ---------------------------------------------------------------------------
# Session context — returned by get_current_session_context
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionContext:
    """
    Carries the authenticated User and their real session_id together.

    Used by the /payments/evaluate endpoint to replace the previously
    hardcoded session_id="sess_api" with the real authenticated session.
    """
    user: User
    session_id: str


# ---------------------------------------------------------------------------
# Adapter singletons — selected once at startup based on USE_LOCAL_ADAPTERS
# ---------------------------------------------------------------------------

def _build_adapters(settings: Settings) -> tuple[
    SessionStoreAdapter,
    StorageAdapter,
    LocalLLMAdapter,      # LLM: always local until Bedrock phase
    AuditStoreAdapter,
    EvidenceStoreAdapter,
    PendingDecisionStoreAdapter,
]:
    """
    Instantiate the correct set of adapters based on configuration.

    Local mode: in-memory stubs — no AWS credentials required.
    AWS mode:   boto3-backed adapters — requires IAM role or credentials.
    """
    if settings.USE_LOCAL_ADAPTERS:
        return (
            LocalSessionStoreAdapter(),
            LocalStorageAdapter(),
            LocalLLMAdapter(),
            LocalAuditStoreAdapter(),
            LocalEvidenceStoreAdapter(),
            LocalPendingDecisionStoreAdapter(),
        )

    # AWS mode — import lazily to avoid boto3 initialisation in local/test contexts
    from .adapters.s3 import S3StorageAdapter
    from .adapters.dynamo import (
        DynamoAuditStoreAdapter,
        DynamoEvidenceStoreAdapter,
        DynamoPendingDecisionStoreAdapter,
        DynamoSessionStoreAdapter,
    )
    from .adapters.bedrock import BedrockAdapter

    return (
        DynamoSessionStoreAdapter(settings),
        S3StorageAdapter(settings),
        BedrockAdapter(settings),           # Real intent + evidence extraction via Claude
        DynamoAuditStoreAdapter(settings),
        DynamoEvidenceStoreAdapter(settings),
        DynamoPendingDecisionStoreAdapter(settings),
    )


_settings = get_settings()
(
    _session_store,
    _storage,
    _llm,
    _audit_store,
    _evidence_store,
    _pending_store,
) = _build_adapters(_settings)


# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

_auth_service       = AuthService(session_store=_session_store)
_intent_service     = IntentService(llm_adapter=_llm)
_evidence_service   = EvidenceService(
    storage_adapter=_storage,
    llm_adapter=_llm,
    evidence_store=_evidence_store,
)
_comparison_service = ComparisonService()
_policy_service     = PolicyService()
_audit_service      = AuditService(audit_store=_audit_store)
_payment_simulator  = PaymentSimulator()
_pending_decision_service = PendingDecisionService(store=_pending_store)
_authorization_service = AuthorizationService(
    intent_service=_intent_service,
    evidence_service=_evidence_service,
    comparison_service=_comparison_service,
    policy_service=_policy_service,
    audit_service=_audit_service,
    payment_simulator=_payment_simulator,
    session_store=_session_store,
    pending_decision_svc=_pending_decision_service,
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


def get_session_store() -> SessionStoreAdapter:
    """Return the active session store adapter (local or DynamoDB)."""
    return _session_store


def get_pending_decision_service() -> PendingDecisionService:
    """Return the pending decision service singleton."""
    return _pending_decision_service


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


async def get_current_session_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
    auth_svc: AuthService = Depends(get_auth_service),
) -> SessionContext:
    """
    FastAPI dependency: validate Bearer token → return SessionContext(user, session_id).

    Used by the /payments/evaluate endpoint to pass the REAL authenticated
    session_id into the authorization pipeline, replacing the previously
    hardcoded 'sess_api'.

    Does NOT weaken authentication — same token validation as get_current_user.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required (Bearer token).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session_id = await auth_svc.validate_token_with_session(credentials.credentials)
    return SessionContext(user=user, session_id=session_id)
