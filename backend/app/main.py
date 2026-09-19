"""
AgentPay Sentinel — FastAPI Application

Entry point. Configures CORS, exception handlers, and mounts all routers.
"""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import get_settings
from .routers import (
    audit_router,
    auth_router,
    evidence_router,
    payments_router,
    policy_router,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured logging — JSON format for CloudWatch, plain format for local dev
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """
    Minimal JSON log formatter for CloudWatch structured log insights.

    Emits one JSON object per log record with fields:
      level, logger, message, timestamp
    Plus any extra dict fields passed via logger.info("...", extra={...}).

    Not used in local mode — plain text is easier to read during development.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        }
        # Merge any extra fields passed by the caller
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                log_data[key] = value
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str)


def _configure_logging(environment: str) -> None:
    """
    Set up application logging.

    - Local:  human-readable format to stdout (default Python behaviour)
    - AWS:    structured JSON to stdout → captured by CloudWatch Logs
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. pytest sets up handlers before import)
        return

    handler = logging.StreamHandler()

    if environment == "local":
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        formatter = _JsonFormatter()

    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Suppress noisy third-party loggers
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.ENVIRONMENT)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Evidence-Aware Trust Gateway for AI-Initiated Payments. "
            "LLMs understand intent and evidence. "
            "The deterministic policy engine makes the final authorization decision."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        contact={"name": "AgentPay Sentinel Team"},
        license_info={"name": "MIT"},
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class CORSDebugMiddleware:
        def __init__(self, app):
            self.app = app
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])}
                logger.info(f"[CORS_DEBUG] {scope.get('method')} {scope.get('path')} | Headers: {json.dumps(headers)}")
            await self.app(scope, receive, send)
    
    app.add_middleware(CORSDebugMiddleware)

    # --- Exception handlers (never expose stack traces to clients) ---

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Request validation failed.",
                "details": exc.errors(),
                "path": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "An internal error occurred. Please try again.",
                "path": str(request.url.path),
            },
        )

    # --- Routers ---
    app.include_router(auth_router)
    app.include_router(payments_router)
    app.include_router(evidence_router)
    app.include_router(audit_router)
    app.include_router(policy_router)

    # --- Health endpoint ---
    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adapter_mode": "local" if settings.USE_LOCAL_ADAPTERS else "aws",
            "sandbox_only": True,
            "disclaimer": (
                "AgentPay Sentinel does not connect to any real payment network. "
                "All payment execution is sandbox simulation only."
            ),
        }

    return app


app = create_app()
