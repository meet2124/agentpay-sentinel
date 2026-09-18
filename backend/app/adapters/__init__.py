"""AgentPay Sentinel — Adapters package"""
from .base import (
    AuditStoreAdapter,
    EvidenceStoreAdapter,
    LLMAdapter,
    SessionStoreAdapter,
    StorageAdapter,
)
from .local import (
    LocalAuditStoreAdapter,
    LocalEvidenceStoreAdapter,
    LocalLLMAdapter,
    LocalSessionStoreAdapter,
    LocalStorageAdapter,
)

__all__ = [
    # Abstract base classes
    "AuditStoreAdapter",
    "EvidenceStoreAdapter",
    "LLMAdapter",
    "SessionStoreAdapter",
    "StorageAdapter",
    # Local implementations
    "LocalAuditStoreAdapter",
    "LocalEvidenceStoreAdapter",
    "LocalLLMAdapter",
    "LocalSessionStoreAdapter",
    "LocalStorageAdapter",
    # AWS implementations (imported lazily in dependencies.py)
    "BedrockAdapter",
]
