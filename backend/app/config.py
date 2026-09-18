"""
AgentPay Sentinel — Application Configuration

All secrets and configuration come from environment variables.
No hardcoded secrets in source code.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # --- Application ---
    APP_NAME: str = "AgentPay Sentinel"
    APP_VERSION: str = "0.2.0"
    ENVIRONMENT: str = "local"                  # local | staging | production
    DEBUG: bool = False

    # --- CORS ---
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Auth (Day 1: API-key based, Day 3: Cognito JWT) ---
    AUTH_MODE: str = "api_key"                  # api_key | cognito
    API_KEY_SALT: str = "sentinel-dev-salt"     # Override in production

    # --- Policy ---
    AMOUNT_MATCH_THRESHOLD_INR: float = 1.0     # |intent - evidence| ≤ ₹1
    PAYEE_MATCH_THRESHOLD: float = 0.85         # fuzzy similarity score threshold
    EVIDENCE_CONFIDENCE_THRESHOLD: float = 0.70 # min extraction confidence
    SMALL_PAYMENT_LIMIT_INR: float = 500.0      # evidence not required below this
    UNKNOWN_PAYEE_MEDIUM_AMOUNT_INR: float = 2000.0  # HRA threshold for new payees

    # --- Adapters ---
    USE_LOCAL_ADAPTERS: bool = True             # False → use real AWS adapters
    LOCAL_DATA_DIR: str = "./local_data"        # In-memory store location

    # --- AWS (used when USE_LOCAL_ADAPTERS=False) ---
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: Optional[str] = None
    DYNAMODB_TABLE_AUDIT: Optional[str] = None
    DYNAMODB_TABLE_SESSIONS: Optional[str] = None
    # Evidence metadata is stored in sentinel-sessions with EVIDENCE# key prefix
    # (2-table design). This variable is kept for future table-split flexibility.
    DYNAMODB_TABLE_EVIDENCE: Optional[str] = None
    BEDROCK_MODEL_ID: str = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"

    # --- Lambda / API Gateway ---
    # Set to the API Gateway stage name (e.g. "prod") when running on Lambda.
    # Used by mangum to strip the stage prefix from request paths.
    LAMBDA_STAGE: str = "local"

    # --- Session ---
    SESSION_TTL_SECONDS: int = 3600             # 1 hour

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
