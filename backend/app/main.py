"""
AgentPay Sentinel — FastAPI Application

Entry point. Configures CORS, exception handlers, and mounts all routers.
"""

from __future__ import annotations

import logging
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


def create_app() -> FastAPI:
    settings = get_settings()

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
